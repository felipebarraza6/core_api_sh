import threading
import time
import requests
import statistics

# Nginx listens on port 80
URL = "http://localhost/admin/login/"
HOST = "api.smarthydro.app"
CONCURRENT_REQUESTS = 20
TOTAL_REQUESTS = 100

def make_request(results):
    start = time.time()
    try:
        # Add Host header to route correctly through nginx-proxy
        headers = {"Host": HOST}
        response = requests.get(URL, headers=headers)
        elapsed = time.time() - start
        results.append({"status": response.status_code, "time": elapsed})
    except Exception as e:
        results.append({"status": str(e), "time": 0})

def run_test():
    print(f"Starting load test: {TOTAL_REQUESTS} requests, {CONCURRENT_REQUESTS} concurrent to {URL} (Host: {HOST})...")
    threads = []
    results = []
    
    start_total = time.time()
    
    for i in range(TOTAL_REQUESTS):
        # Throttle creation slightly to not overwhelm local system if single-threaded creation
        if len(threads) >= CONCURRENT_REQUESTS:
            for t in threads:
                t.join()
            threads = []
        
        t = threading.Thread(target=make_request, args=(results,))
        threads.append(t)
        t.start()
            
    # Cleanup remaining
    for t in threads:
        t.join()
        
    end_total = time.time()
    
    # Count 200 OK and 302 Found (redirects) as success
    times = [r["time"] for r in results if isinstance(r["status"], int) and r["status"] in [200, 301, 302]]
    errors = [r for r in results if not (isinstance(r["status"], int) and r["status"] in [200, 301, 302])]
    
    print(f"\n--- Results ---")
    print(f"Total Time: {end_total - start_total:.2f}s")
    print(f"Successful Requests: {len(times)}")
    print(f"Errors: {len(errors)}")
    if errors:
        print(f"Sample Error: {errors[0]['status']}")
        
    if times:
        print(f"Avg Time: {statistics.mean(times):.3f}s")
        print(f"Min Time: {min(times):.3f}s")
        print(f"Max Time: {max(times):.3f}s")
        print(f"Requests/sec: {len(times) / (end_total - start_total):.2f}")
    else:
        print("No successful requests")

if __name__ == "__main__":
    run_test()
