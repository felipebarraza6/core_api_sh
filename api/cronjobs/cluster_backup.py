# Lightweight wrapper to the stable implementation
# Do not remove: other tooling may still reference this module path.
from api.cronjobs.cluster_backup_complete_final import run as _stable_run

def run():
    return _stable_run()

if __name__ == "__main__":
    run()
