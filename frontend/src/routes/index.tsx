import { Routes, Route, Navigate } from 'react-router-dom'
import { MainLayout } from '@/app/MainLayout'
import { PricingSandboxPage } from '@/features/pricing/PricingSandboxPage'
import { ContractsPage } from '@/features/contracts/ContractsPage'
import { ContractDetailPage } from '@/features/contracts/ContractDetailPage'
import { ContractExplorerPage } from '@/features/contracts/ContractExplorerPage'
import { RulesPage } from '@/features/rules/RulesPage'
import { RuleDetailPage } from '@/features/rules/RuleDetailPage'
import { RuleCreatePage } from '@/features/rules/RuleCreatePage'
import { RuleSimulatorPage } from '@/features/simulation/RuleSimulatorPage'
import { RunScenarioPage } from '@/features/simulation/RunScenarioPage'
import { ClaimSimulationPage } from '@/features/simulation/ClaimSimulationPage'
import { RepriceClaimPage } from '@/features/reprice/RepriceClaimPage'
import { BatchRepricePage } from '@/features/reprice/BatchRepricePage'
import { ProvidersPage } from '@/features/providers/ProvidersPage'
import { MemberLookupPage } from '@/features/members/MemberLookupPage'
import { ProductsPage } from '@/features/products/ProductsPage'
import { BatchMonitorPage } from '@/features/monitoring/BatchMonitorPage'
import { AdminPage } from '@/features/admin/AdminPage'

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<MainLayout />}>
        <Route index element={<Navigate to="/pricing-sandbox" replace />} />
        <Route path="pricing-sandbox" element={<PricingSandboxPage />} />
        <Route path="contracts/:contractId/rules/new" element={<RuleCreatePage />} />
        <Route path="contracts/:id" element={<ContractDetailPage />} />
        <Route path="contract-explorer" element={<ContractExplorerPage />} />
        <Route path="contracts" element={<ContractsPage />} />
        <Route path="rules" element={<RulesPage />} />
        <Route path="rules/:id" element={<RuleDetailPage />} />
        <Route path="claim-simulation" element={<ClaimSimulationPage />} />
        <Route path="reprice-claim" element={<RepriceClaimPage />} />
        <Route path="batch-reprice" element={<BatchRepricePage />} />
        <Route path="providers" element={<ProvidersPage />} />
        <Route path="members" element={<MemberLookupPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="rule-simulator" element={<RuleSimulatorPage />} />
        <Route path="run-scenario" element={<RunScenarioPage />} />
        <Route path="batch-monitor" element={<BatchMonitorPage />} />
        <Route path="admin" element={<AdminPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
