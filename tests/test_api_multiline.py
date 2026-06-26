from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from decimal import Decimal

# We reuse the setup logic from your existing utils to keep tests consistent
from .utils import MatrixPricingEngine

class MultiLineAPITests(MatrixPricingEngine, APITestCase):
    """
    Validates the Batch Pricing Endpoint: POST /api/price-claim/
    """
    def setUp(self):
        # This creates the Contract, Provider, and RBRVS Rule for '99213'
        super().setUp() 
        self.url = reverse('price-claim') # Matches urls.py name='price-claim'

    def test_price_claim_success(self):
        """
        Scenario: Send a claim with 2 identical lines.
        Expected: 
            - 200 OK
            - Both lines priced at $150.00 (RBRVS calculation)
            - Total Allowed = $300.00
        """
        payload = {
            "contract_id": self.contract.pk,
            "lines": [
                {
                    "line_id": "LINE-001",
                    "procedure_code": "99213",
                    "billed_amount": 200.00,
                    "units": 1,
                    "modifiers": []
                },
                {
                    "line_id": "LINE-002",
                    "procedure_code": "99213",
                    "billed_amount": 200.00,
                    "units": 1,
                    "modifiers": ["25"]
                }
            ]
        }

        # Act
        response = self.client.post(self.url, payload, format='json')

        # Assert Structure
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_allowed', response.data)
        self.assertIn('lines', response.data)
        self.assertEqual(len(response.data['lines']), 2)

        # Assert Logic (The "Enterprise" Check)
        # We expect $150.00 per line (1.5 multiplier * 100.00 base)
        expected_line_price = Decimal("150.00")
        expected_total = expected_line_price * 2

        self.assertEqual(Decimal(str(response.data['total_allowed'])), expected_total)
        self.assertEqual(Decimal(str(response.data['lines'][0]['allowed_amount'])), expected_line_price)

        # Assert Traceability (The "Audit" Check)
        self.assertEqual(str(response.data['contract_id']), str(self.contract.pk))
        self.assertEqual(response.data['lines'][0]['status'], "SUCCESS")

    def test_price_claim_empty_lines(self):
        """
        Scenario: Send a valid contract but empty lines list.
        Expected: 200 OK with $0 total (or 400 Bad Request depending on design).
        Current Design: 200 OK with 0 total.
        """
        payload = {
            "contract_id": self.contract.pk,
            "lines": []
        }
        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # ClaimPricingResultSerializer may return total_allowed as string "0.00" or number 0
        total = response.data.get('total_allowed')
        self.assertTrue(total == 0 or total == "0" or total == "0.00" or (isinstance(total, (int, float)) and float(total) == 0))
        self.assertEqual(len(response.data.get('lines', [])), 0)

    def test_price_claim_invalid_contract(self):
        """
        Scenario: Send a non-existent contract ID.
        Expected: 404 Not Found.
        """
        payload = {
            "contract_id": 99999,
            "lines": [{"procedure_code": "99213", "billed_amount": 100}]
        }
        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)