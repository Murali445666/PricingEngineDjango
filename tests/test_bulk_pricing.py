"""
Step 11 Milestone C — Bulk Pricing Tests

Validates:
  1. price_claims_bulk() prices N claims correctly (results match individual pricing).
  2. ContractPricingConfig is built ONCE per (contract, version, service_date) even
     when N > 1 claims share the same key (config reuse verified via mock call count).
  3. Per-claim execution cache isolation — no state bleed across claims in the batch.
  4. POST /api/price-claims-bulk/ returns correct structure and totals.
  5. Regression: existing single-claim endpoint results unchanged.
"""
from decimal import Decimal
from unittest.mock import patch, call
from datetime import date

from django.urls import reverse
from rest_framework import status as http_status
from rest_framework.test import APITestCase

from core.engine.service import ClaimPricingService
from core.engine.config import ClaimPricingInput, ClaimLineInput
from core.engine.loader import build_contract_pricing_config_from_db

from .utils import MatrixPricingEngine


class BulkPricingServiceTests(MatrixPricingEngine):
    """
    Unit-level tests for ClaimPricingService.price_claims_bulk().
    Uses the Matrix test contract with RBRVS, FLAT_RATE, and PERCENT_BILLED rules.
    """

    # ------------------------------------------------------------------ helpers

    def _make_claim(self, lines, service_date=None):
        return ClaimPricingInput(
            contract_id=self.contract.pk,
            contract=self.contract,
            service_date=service_date or date(2025, 6, 1),
            claim_id=None,
            lines=lines,
        )

    def _rbrvs_line(self, units=1):
        # 99213 → RBRVS, base_rate=100, multiplier=1.50 → expected $150.00
        return ClaimLineInput(procedure_code="99213", billed_amount=Decimal("200.00"), units=units)

    def _flat_line(self):
        # 73030 → FLAT_RATE, flat_rate=$75.00
        return ClaimLineInput(procedure_code="73030", billed_amount=Decimal("100.00"), units=1)

    def _pct_line(self):
        # 29806 → PERCENT_BILLED, multiplier=0.50, billed=$1000 → $500.00
        return ClaimLineInput(procedure_code="29806", billed_amount=Decimal("1000.00"), units=1)

    # ------------------------------------------------------------------ tests

    def test_bulk_single_claim_matches_individual(self):
        """Bulk of one claim must equal individual price_claim() result."""
        service = ClaimPricingService()
        claim_input = self._make_claim([self._rbrvs_line()])

        individual = service.price_claim(
            ClaimPricingInput(
                contract_id=self.contract.pk,
                contract=self.contract,
                service_date=date(2025, 6, 1),
                lines=[self._rbrvs_line()],
            )
        )
        bulk_results = service.price_claims_bulk([claim_input])

        self.assertEqual(len(bulk_results), 1)
        self.assertEqual(bulk_results[0].total_allowed, individual.total_allowed)
        self.assertEqual(bulk_results[0].status, individual.status)

    def test_bulk_three_claims_same_contract_correct_totals(self):
        """
        Three claims on the same contract — each priced independently and correctly.
        Claim A: 1 × 99213 = $150.00
        Claim B: 1 × 73030 = $75.00
        Claim C: 1 × 29806 @ $1000 billed = $500.00
        """
        service = ClaimPricingService()
        claim_a = self._make_claim([self._rbrvs_line()])
        claim_b = self._make_claim([self._flat_line()])
        claim_c = self._make_claim([self._pct_line()])

        results = service.price_claims_bulk([claim_a, claim_b, claim_c])

        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].total_allowed, Decimal("150.00"))
        self.assertEqual(results[1].total_allowed, Decimal("75.00"))
        self.assertEqual(results[2].total_allowed, Decimal("500.00"))

    def test_bulk_config_built_once_per_contract_version_date(self):
        """
        ContractPricingConfig is built exactly ONCE even when multiple claims share
        the same (contract, version, service_date). Verified via mock call count.
        """
        service = ClaimPricingService()
        claims = [
            self._make_claim([self._rbrvs_line()]),
            self._make_claim([self._flat_line()]),
            self._make_claim([self._rbrvs_line()]),
        ]

        target = "core.engine.service.build_contract_pricing_config_from_db"
        with patch(target, wraps=build_contract_pricing_config_from_db) as mock_build:
            results = service.price_claims_bulk(claims)
            self.assertEqual(
                mock_build.call_count,
                1,
                "ContractPricingConfig must be built once per unique (contract, version, service_date).",
            )

        self.assertEqual(len(results), 3)

    def test_bulk_config_built_once_per_unique_date(self):
        """
        When claims have DIFFERENT service_dates, config is built once per unique date.
        Two distinct dates → two config builds.
        """
        service = ClaimPricingService()
        claims = [
            self._make_claim([self._rbrvs_line()], service_date=date(2025, 1, 1)),
            self._make_claim([self._rbrvs_line()], service_date=date(2025, 1, 1)),
            self._make_claim([self._flat_line()], service_date=date(2025, 6, 1)),
        ]

        target = "core.engine.service.build_contract_pricing_config_from_db"
        with patch(target, wraps=build_contract_pricing_config_from_db) as mock_build:
            service.price_claims_bulk(claims)
            self.assertEqual(
                mock_build.call_count,
                2,
                "Config must be built once per unique (contract, version, service_date) pair.",
            )

    def test_bulk_execution_cache_reset_per_claim(self):
        """
        Execution cache isolation: pricing results must be independent even when
        the same procedure code appears in multiple claims within the same batch.
        Each claim priced at correct independent amount.
        """
        service = ClaimPricingService()
        # Same procedure code in each claim → cache hit within a claim is fine,
        # but state from claim N must not leak into claim N+1.
        claims = [self._make_claim([self._rbrvs_line(), self._rbrvs_line()]) for _ in range(3)]
        results = service.price_claims_bulk(claims)

        for i, result in enumerate(results):
            self.assertEqual(
                result.total_allowed,
                Decimal("300.00"),
                f"Claim {i} total mismatch; possible cache bleed from prior claim.",
            )

    def test_bulk_empty_list_returns_empty(self):
        """price_claims_bulk([]) must return an empty list immediately."""
        service = ClaimPricingService()
        self.assertEqual(service.price_claims_bulk([]), [])

    def test_bulk_multiline_claim(self):
        """Multi-line claim in a batch: total equals sum of line prices."""
        service = ClaimPricingService()
        claim = self._make_claim([self._rbrvs_line(), self._flat_line()])
        results = service.price_claims_bulk([claim])

        self.assertEqual(len(results), 1)
        # 99213 → $150.00 + 73030 → $75.00 = $225.00
        self.assertEqual(results[0].total_allowed, Decimal("225.00"))
        self.assertEqual(results[0].line_count, 2)


class BulkPricingAPITests(MatrixPricingEngine, APITestCase):
    """
    Integration tests for POST /api/price-claims-bulk/.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('price-claims-bulk')

    def _rbrvs_payload(self):
        return {"procedure_code": "99213", "billed_amount": "200.00", "units": 1}

    def _flat_payload(self):
        return {"procedure_code": "73030", "billed_amount": "100.00", "units": 1}

    def test_bulk_api_success_two_claims(self):
        """
        Two claims on the same contract via the API endpoint.
        Verifies response structure, total counts, and per-claim totals.
        """
        payload = {
            "claims": [
                {
                    "contract_id": self.contract.pk,
                    "service_date": "2025-06-01",
                    "lines": [self._rbrvs_payload()],
                },
                {
                    "contract_id": self.contract.pk,
                    "service_date": "2025-06-01",
                    "lines": [self._flat_payload()],
                },
            ]
        }
        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)

        data = response.data
        self.assertEqual(data['total_claims'], 2)
        self.assertEqual(data['priced_claims'], 2)
        self.assertEqual(len(data['results']), 2)
        self.assertIn('request_time_ms', data)

        self.assertEqual(Decimal(str(data['results'][0]['total_allowed'])), Decimal("150.00"))
        self.assertEqual(Decimal(str(data['results'][1]['total_allowed'])), Decimal("75.00"))

    def test_bulk_api_three_identical_claims_config_reuse(self):
        """
        Three identical claims on the same contract and date.
        All should return the same pricing result.
        """
        single_claim = {
            "contract_id": self.contract.pk,
            "service_date": "2025-06-01",
            "lines": [self._rbrvs_payload()],
        }
        payload = {"claims": [single_claim, single_claim, single_claim]}
        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data['total_claims'], 3)
        for result in data['results']:
            self.assertEqual(Decimal(str(result['total_allowed'])), Decimal("150.00"))
            self.assertEqual(result['status'], 'SUCCESS')

    def test_bulk_api_invalid_contract_returns_404(self):
        """A batch containing an unknown contract_id must return 404."""
        payload = {
            "claims": [
                {"contract_id": 99999, "lines": [self._rbrvs_payload()]},
            ]
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_404_NOT_FOUND)

    def test_bulk_api_empty_claims_list_returns_400(self):
        """An empty claims list must be rejected (min_length=1 validation)."""
        payload = {"claims": []}
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_400_BAD_REQUEST)

    def test_bulk_api_results_match_individual_endpoint(self):
        """
        Regression: bulk result for one claim must equal POST /api/price-claim/ result.
        """
        single_payload = {
            "contract_id": self.contract.pk,
            "service_date": "2025-06-01",
            "lines": [self._rbrvs_payload()],
        }

        # Individual endpoint
        individual_response = self.client.post(
            reverse('price-claim'), single_payload, format='json'
        )
        self.assertEqual(individual_response.status_code, http_status.HTTP_200_OK)
        individual_total = Decimal(str(individual_response.data['total_allowed']))

        # Bulk endpoint (batch of one)
        bulk_response = self.client.post(
            self.url, {"claims": [single_payload]}, format='json'
        )
        self.assertEqual(bulk_response.status_code, http_status.HTTP_200_OK)
        bulk_total = Decimal(str(bulk_response.data['results'][0]['total_allowed']))

        self.assertEqual(
            individual_total,
            bulk_total,
            "Bulk result must match individual endpoint for the same claim.",
        )

    def test_bulk_api_multiline_claim(self):
        """Multi-line claim in a batch returns correct sum."""
        payload = {
            "claims": [
                {
                    "contract_id": self.contract.pk,
                    "service_date": "2025-06-01",
                    "lines": [self._rbrvs_payload(), self._flat_payload()],
                }
            ]
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, http_status.HTTP_200_OK)
        # 99213=$150 + 73030=$75 = $225
        self.assertEqual(
            Decimal(str(response.data['results'][0]['total_allowed'])),
            Decimal("225.00"),
        )
        self.assertEqual(response.data['results'][0]['line_count'], 2)
