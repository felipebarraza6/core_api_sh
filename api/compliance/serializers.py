from rest_framework import serializers
from .models import (
    ComplianceProvider, 
    PointComplianceConfig, 
    ComplianceVoucher,
    CompliancePeriod
)

class ComplianceProviderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceProvider
        fields = ['id', 'name', 'display_name', 'service_type', 'is_active']

class PointComplianceConfigSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source='provider.display_name', read_only=True)
    compliance_standard_name = serializers.CharField(source='compliance_standard.name', read_only=True)
    
    class Meta:
        model = PointComplianceConfig
        fields = [
            'id', 'point', 'provider', 'provider_name', 
            'compliance_standard', 'compliance_standard_name',
            'is_active', 'send_compliance', 
            'last_submission', 'last_success', 'last_error',
            'error_count', 'total_submissions'
        ]
        read_only_fields = ['last_submission', 'last_success', 'last_error', 'error_count', 'total_submissions']

class ComplianceVoucherSerializer(serializers.ModelSerializer):
    provider_code = serializers.CharField(source='provider.name', read_only=True)
    
    class Meta:
        model = ComplianceVoucher
        fields = [
            'id', 'point', 'provider_code', 
            'data_timestamp', 'data_snapshot',
            'voucher_status', 'voucher_code', 
            'error_message', 'generated_at'
        ]
        read_only_fields = ['__all__'] # Vouchers are immutable evidence

class CompliancePeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompliancePeriod
        fields = ['id', 'point', 'name', 'valid_from', 'valid_to', 'is_active']
