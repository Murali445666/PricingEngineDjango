from django.urls import path
from core.api.views import ContractListView, PriceLineView, PriceClaimView

urlpatterns = [
    path('contracts/', ContractListView.as_view(), name='api-contract-list'),
    path('price-line/', PriceLineView.as_view(), name='api-price-line'),
    path('price-claim/', PriceClaimView.as_view(), name='price-claim'),
]
