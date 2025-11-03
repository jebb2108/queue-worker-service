import pytest
from unittest.mock import patch
from src.infrastructure.services import PrometheusMetricsCollector


class TestPrometheusMetricsCollector:
    """Тесты для PrometheusMetricsCollector"""

    def test_init_creates_metrics(self, metrics_collector):
        """Тест инициализации метрик"""
        # Проверяем, что все метрики созданы
        assert hasattr(metrics_collector, 'registry')
        assert hasattr(metrics_collector, 'queue_size')
        assert hasattr(metrics_collector, 'queue_wait_time')
        assert hasattr(metrics_collector, 'match_attempts_total')
        assert hasattr(metrics_collector, 'matches_found_total')
        assert hasattr(metrics_collector, 'compatibility_score')
        assert hasattr(metrics_collector, 'processing_time')
        assert hasattr(metrics_collector, 'candidates_evaluated')
        assert hasattr(metrics_collector, 'errors_total')
        assert hasattr(metrics_collector, 'retry_attempts_total')
        assert hasattr(metrics_collector, 'retry_delay')
        assert hasattr(metrics_collector, 'active_users')
        assert hasattr(metrics_collector, 'criteria_usage')

    @pytest.mark.asyncio
    async def test_record_match_attempt_success(self, metrics_collector):
        """Тест записи успешной попытки матчинга"""
        user_id = 1
        processing_time = 0.5
        candidates_evaluated = 10
        match_found = True
        compatibility_score = 0.85

        await metrics_collector.record_match_attempt(
            user_id=user_id,
            processing_time=processing_time,
            candidates_evaluated=candidates_evaluated,
            match_found=match_found,
            compatibility_score=compatibility_score
        )

        # Проверяем, что метрики записаны (через get_metrics)
        metrics = await metrics_collector.get_metrics()
        assert 'prometheus_metrics' in metrics
        assert isinstance(metrics['prometheus_metrics'], str)

    @pytest.mark.asyncio
    async def test_record_match_attempt_failure(self, metrics_collector):
        """Тест записи неудачной попытки матчинга"""
        user_id = 2
        processing_time = 2.0
        candidates_evaluated = 50
        match_found = False

        await metrics_collector.record_match_attempt(
            user_id=user_id,
            processing_time=processing_time,
            candidates_evaluated=candidates_evaluated,
            match_found=match_found
        )

        # Проверяем, что метрики записаны
        metrics = await metrics_collector.get_metrics()
        assert 'prometheus_metrics' in metrics

