"""
Celery Tasks for Report Generation
Replaces cronjobs/reports/ with scalable report system
"""

import logging
from celery import shared_task
from django.utils import timezone
from datetime import datetime, timedelta, date
import time
import os

from api.core.models import TelemetryRecord, CatchmentPoint
from api.telemetry.services.telemetry_service import TelemetryService

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2)
def generate_daily_bulletin(self):
    """
    Generate daily telemetry bulletin (V3)
    """
    try:
        logger.info("Starting daily bulletin generation (V3)")

        yesterday = timezone.now().date() - timedelta(days=1)
        start_time = time.time()

        # Generate bulletin data
        bulletin_data = generate_bulletin_data(yesterday)

        # Save or send bulletin
        save_daily_bulletin(bulletin_data, yesterday)

        execution_time = time.time() - start_time
        logger.info(f"Daily bulletin generated in {execution_time:.2f}s")

        return {
            "date": yesterday.isoformat(),
            "points_reported": len(bulletin_data.get("points", [])),
            "execution_time": execution_time,
        }

    except Exception as exc:
        logger.error(f"Daily bulletin generation failed: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=2)
def generate_daily_chat_report(self):
    """
    Generate daily chat report for Google Chat (V3)
    """
    try:
        logger.info("Starting daily chat report generation (V3)")

        yesterday = timezone.now().date() - timedelta(days=1)
        start_time = time.time()

        # Generate report data
        report_data = generate_chat_report_data(yesterday)

        # Send to Google Chat
        send_to_google_chat(report_data)

        execution_time = time.time() - start_time
        logger.info(f"Daily chat report generated in {execution_time:.2f}s")

        return {
            "date": yesterday.isoformat(),
            "points_reported": len(report_data.get("points", [])),
            "execution_time": execution_time,
        }

    except Exception as exc:
        logger.error(f"Daily chat report generation failed: {exc}")
        self.retry(countdown=300, exc=exc)


@shared_task(bind=True, max_retries=2)
def generate_dga_major_hourly(self):
    """
    Generate hourly DGA report for major points (V3)
    """
    try:
        logger.info("Starting DGA major hourly report (V3)")

        # Report for the previous hour
        report_hour = timezone.now().replace(
            minute=0, second=0, microsecond=0
        ) - timedelta(hours=1)
        start_time = time.time()

        # Generate report data
        report_data = generate_dga_hourly_data(report_hour)

        # Save or send report
        save_dga_hourly_report(report_data, report_hour)

        execution_time = time.time() - start_time
        logger.info(f"DGA hourly report generated in {execution_time:.2f}s")

        return {
            "report_hour": report_hour.isoformat(),
            "points_reported": len(report_data.get("points", [])),
            "execution_time": execution_time,
        }

    except Exception as exc:
        logger.error(f"DGA hourly report generation failed: {exc}")
        self.retry(countdown=60, exc=exc)


def generate_bulletin_data(target_date):
    """
    Generate comprehensive bulletin data for a date (V3)
    """
    try:
        start_datetime = timezone.make_aware(
            datetime.combine(target_date, datetime.min.time())
        )
        end_datetime = start_datetime + timedelta(days=1)

        # Get all points with data for the day
        points_with_data = (
            CatchmentPoint.objects.filter(telemetry_v3__timestamp__date=target_date)
            .distinct()
            .select_related("project", "project__client")
        )

        bulletin = {
            "date": target_date.isoformat(),
            "points": [],
            "summary": {
                "total_points": 0,
                "points_with_errors": 0,
                "total_readings": 0,
            },
        }

        for point in points_with_data:
            point_data = generate_point_daily_summary(
                point, start_datetime, end_datetime
            )
            bulletin["points"].append(point_data)

            # Update summary
            bulletin["summary"]["total_points"] += 1
            if point_data.get("had_errors", False):
                bulletin["summary"]["points_with_errors"] += 1
            bulletin["summary"]["total_readings"] += point_data.get(
                "reading_count", 0
            )

        return bulletin

    except Exception as exc:
        logger.error(f"Error generating bulletin data: {exc}")
        return {}


def generate_point_daily_summary(point, start_datetime, end_datetime):
    """
    Generate daily summary for a single point (V3)
    """
    try:
        # Get daily readings
        readings = TelemetryRecord.objects.filter(
            point=point, timestamp__gte=start_datetime, timestamp__lt=end_datetime
        ).order_by("timestamp")

        if not readings.exists():
            return {
                "point_id": point.id,
                "point_name": point.title,
                "reading_count": 0,
                "had_errors": False,
                "no_data": True,
            }

        # Calculate statistics
        flow_readings = [
            float(r.data.get("flow", 0))
            for r in readings
            if r.data.get("flow") is not None
        ]
        level_readings = [
            float(r.data.get("nivel", 0))
            for r in readings
            if r.data.get("nivel") is not None
        ]

        return {
            "point_id": point.id,
            "point_name": point.title,
            "project": point.project.name if point.project else None,
            "client": point.project.client.name
            if point.project and point.project.client
            else None,
            "reading_count": len(readings),
            "error_count": sum(1 for r in readings if r.is_error),
            "had_errors": any(r.is_error for r in readings),
            "flow_stats": {
                "min": min(flow_readings) if flow_readings else None,
                "max": max(flow_readings) if flow_readings else None,
                "avg": sum(flow_readings) / len(flow_readings)
                if flow_readings
                else None,
            },
            "level_stats": {
                "min": min(level_readings) if level_readings else None,
                "max": max(level_readings) if level_readings else None,
                "avg": sum(level_readings) / len(level_readings)
                if level_readings
                else None,
            },
            "first_reading": readings.first().timestamp.isoformat(),
            "last_reading": readings.last().timestamp.isoformat(),
        }

    except Exception as exc:
        logger.error(f"Error generating point summary for {point.id}: {exc}")
        return {"point_id": point.id, "point_name": point.title, "error": str(exc)}


def generate_chat_report_data(target_date):
    """
    Generate simplified data for Google Chat report
    """
    try:
        bulletin = generate_bulletin_data(target_date)

        # Format for chat
        chat_report = {
            'date': target_date.isoformat(),
            'summary': bulletin.get('summary', {}),
            'alerts': []
        }

        # Add critical alerts
        for point_data in bulletin.get('points', []):
            if point_data.get('had_errors', False):
                chat_report['alerts'].append({
                    'point': point_data['point_name'],
                    'errors': point_data['error_count'],
                    'readings': point_data['reading_count']
                })

        return chat_report

    except Exception as exc:
        logger.error(f"Error generating chat report data: {exc}")
        return {}


def generate_dga_hourly_data(report_hour):
    """
    Generate DGA hourly report data (V3)
    """
    try:
        from django.db.models import Avg

        start_time = report_hour
        end_time = report_hour + timedelta(hours=1)

        # Get major DGA points
        dga_points = CatchmentPoint.objects.filter(
            dga_config__send_dga=True
        ).select_related("dga_config")

        report = {"hour": report_hour.isoformat(), "points": []}

        for point in dga_points:
            # Get readings for the hour in V3
            readings = TelemetryRecord.objects.filter(
                point=point,
                timestamp__gte=start_time,
                timestamp__lt=end_time,
                send_dga=True,
            )

            if readings.exists():
                # Aggregating JSON data is tricky, we might need to do it in Python
                # or use a complex extra/raw query. For now, Python is safer.
                flow_list = [
                    float(r.data.get("flow", 0))
                    for r in readings
                    if r.data.get("flow") is not None
                ]
                nivel_list = [
                    float(r.data.get("nivel", 0))
                    for r in readings
                    if r.data.get("nivel") is not None
                ]

                point_report = {
                    "point_id": point.id,
                    "point_name": point.title,
                    "dga_code": point.dga_config.code_dga,
                    "readings_submitted": readings.count(),
                    "flow_avg": sum(flow_list) / len(flow_list) if flow_list else 0,
                    "level_avg": sum(nivel_list) / len(nivel_list)
                    if nivel_list
                    else 0,
                    "errors": readings.filter(is_error=True).count(),
                }
                report["points"].append(point_report)

        return report

    except Exception as exc:
        logger.error(f"Error generating DGA hourly data: {exc}")
        return {}


def save_daily_bulletin(bulletin_data, target_date):
    """
    Save daily bulletin to file or database
    """
    try:
        # Save to media/reports/ directory
        filename = f"daily_bulletin_{target_date.isoformat()}.json"
        filepath = os.path.join('media', 'reports', filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(bulletin_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Daily bulletin saved to {filepath}")

    except Exception as exc:
        logger.error(f"Error saving daily bulletin: {exc}")


def send_to_google_chat(report_data):
    """
    Send report to Google Chat
    """
    try:
        # Implementation depends on Google Chat webhook setup
        # This is a placeholder for the actual implementation
        logger.info("Google Chat report sent (placeholder)")

    except Exception as exc:
        logger.error(f"Error sending to Google Chat: {exc}")


def save_dga_hourly_report(report_data, report_hour):
    """
    Save DGA hourly report
    """
    try:
        filename = f"dga_hourly_{report_hour.strftime('%Y%m%d_%H')}.json"
        filepath = os.path.join('media', 'reports', 'dga', filename)

        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        logger.info(f"DGA hourly report saved to {filepath}")

    except Exception as exc:
        logger.error(f"Error saving DGA hourly report: {exc}")