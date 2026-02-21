from django.urls import path
from core.api.views import (
    ContractListView,
    ContractDetailView,
    ContractRuleListView,
    RuleListView,
    RuleDetailView,
    RuleHistoryView,
    RuleConflictsView,
    RuleCheckConflictsView,
    FeeScheduleListView,
    ProcedureCodeListView,
    ModifierListView,
    PriceLineView,
    PriceClaimView,
    SimulateLineView,
)

urlpatterns = [
    path('contracts/', ContractListView.as_view(), name='api-contract-list'),
    path('contracts/<int:pk>/', ContractDetailView.as_view(), name='api-contract-detail'),
    path('contracts/<int:pk>/rules/', ContractRuleListView.as_view(), name='api-contract-rules'),
    path('fee-schedules/', FeeScheduleListView.as_view(), name='api-fee-schedules'),
    path('procedure-codes/', ProcedureCodeListView.as_view(), name='api-procedure-codes'),
    path('modifiers/', ModifierListView.as_view(), name='api-modifiers'),
    path('rules/', RuleListView.as_view(), name='api-rule-list'),
    path('rules/check-conflicts/', RuleCheckConflictsView.as_view(), name='api-rule-check-conflicts'),
    path('rules/<int:pk>/', RuleDetailView.as_view(), name='api-rule-detail'),
    path('rules/<int:pk>/conflicts/', RuleConflictsView.as_view(), name='api-rule-conflicts'),
    path('rules/<int:rule_id>/history/', RuleHistoryView.as_view(), name='api-rule-history'),
    path('price-line/', PriceLineView.as_view(), name='api-price-line'),
    path('simulate-line/', SimulateLineView.as_view(), name='api-simulate-line'),
    path('price-claim/', PriceClaimView.as_view(), name='price-claim'),
]
