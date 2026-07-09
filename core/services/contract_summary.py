"""
Read-only contract summary assembly for the layered contract model (§13).
Does not query the pricing engine or mutate data.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from django.core.exceptions import ObjectDoesNotExist

from core.models import (
    ContractAmendment,
    ContractArrangement,
    ContractCapFloor,
    ContractCarveout,
    ContractCoveredEntity,
    ContractDocument,
    ContractOutlierRule,
    ContractProductScope,
    ContractRateBasis,
    ContractScope,
    ContractStopLossRule,
    PricingRule,
    PricingRuleCondition,
    ProviderContract,
)
from core.services.rate_materialization import (
    compose_rate_basis_label,
    default_target_year,
    find_applicable_escalator,
)


def _serialize_payer_org(payer_org) -> Optional[dict[str, Any]]:
    if payer_org is None:
        return None
    return {
        'id': payer_org.id,
        'name': payer_org.name,
        'payer_id': payer_org.payer_id,
        'payer_type': payer_org.payer_type,
    }


def _serialize_provider_org(org) -> dict[str, Any]:
    parent_name = None
    if getattr(org, 'parent_org_id', None) and getattr(org, 'parent_org', None):
        parent_name = org.parent_org.name
    return {
        'organization_id': org.organization_id,
        'name': org.name,
        'npi': org.npi,
        'org_type': getattr(org, 'org_type', None),
        'parent_org_id': org.parent_org_id,
        'parent_org_name': parent_name,
    }


def _serialize_network(network) -> dict[str, Any]:
    return {
        'network_id': network.network_id,
        'network_name': network.network_name,
        'line_of_business': network.line_of_business,
        'network_type': network.network_type,
    }


def _serialize_document(doc: ContractDocument) -> dict[str, Any]:
    return {
        'id': doc.id,
        'doc_type': doc.doc_type,
        'reference': doc.reference,
        'title': doc.title,
        'notes': doc.notes,
        'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
    }


def _covered_entity_label(entity: ContractCoveredEntity) -> tuple[str, str]:
    """Return (name, detail) for abstract and frontend display."""
    if entity.entity_type == ContractCoveredEntity.EntityType.ORG and entity.organization_id:
        org = entity.organization
        detail = org.npi or org.organization_id
        return org.name, detail
    if entity.entity_type == ContractCoveredEntity.EntityType.FACILITY and entity.facility_id:
        fac = entity.facility
        return fac.name, fac.npi
    if entity.entity_type == ContractCoveredEntity.EntityType.PROVIDER and entity.provider_id:
        prov = entity.provider
        name = f'Dr. {prov.first_name} {prov.last_name}'.strip()
        return name, prov.npi
    return entity.entity_type, ''


def _serialize_covered_entity(entity: ContractCoveredEntity) -> dict[str, Any]:
    name, detail = _covered_entity_label(entity)
    payload: dict[str, Any] = {
        'id': entity.id,
        'entity_type': entity.entity_type,
        'name': name,
        'detail': detail,
        'is_primary': entity.is_primary,
        'effective_start_date': (
            entity.effective_start_date.isoformat() if entity.effective_start_date else None
        ),
        'effective_end_date': (
            entity.effective_end_date.isoformat() if entity.effective_end_date else None
        ),
    }
    if entity.entity_type == ContractCoveredEntity.EntityType.ORG and entity.organization_id:
        payload['organization'] = _serialize_provider_org(entity.organization)
    elif entity.entity_type == ContractCoveredEntity.EntityType.FACILITY and entity.facility_id:
        payload['facility'] = {
            'id': entity.facility.id,
            'npi': entity.facility.npi,
            'name': entity.facility.name,
            'facility_type': entity.facility.facility_type,
        }
    elif entity.entity_type == ContractCoveredEntity.EntityType.PROVIDER and entity.provider_id:
        payload['provider'] = {
            'id': entity.provider.id,
            'npi': entity.provider.npi,
            'first_name': entity.provider.first_name,
            'last_name': entity.provider.last_name,
        }
    return payload


def _serialize_rule(rule: PricingRule, materialized_year: Optional[int] = None) -> dict[str, Any]:
    conditions = list(
        PricingRuleCondition.objects.filter(pricing_rule=rule).order_by('condition_id')
    )
    codes = [
        c.attribute_value
        for c in conditions
        if c.attribute_name == 'procedure_code' and c.attribute_value
    ]
    rate: str | None = None
    if rule.flat_rate is not None:
        rate = f'${rule.flat_rate}'
    elif rule.multiplier is not None:
        rate = f'{rule.multiplier}× billed'
    elif rule.methodology_code:
        rate = rule.methodology_code

    rate_basis: str | None = None
    mat_year: int | None = None
    try:
        basis: ContractRateBasis = rule.rate_basis
        year = materialized_year
        if year is None:
            year = default_target_year(basis.schedule)
        escalator = find_applicable_escalator(rule.contract, rule.version_id, year)
        rate_basis = compose_rate_basis_label(basis, escalator)
        mat_year = year
    except ContractRateBasis.DoesNotExist:
        pass

    return {
        'rule_id': rule.rule_id,
        'rule_name': rule.rule_name,
        'rule_type': rule.rule_type,
        'methodology_code': rule.methodology_code,
        'status': rule.status,
        'claim_type': rule.claim_type,
        'specificity_score': rule.specificity_score,
        'codes': codes,
        'rate': rate,
        'rate_basis': rate_basis,
        'materialized_year': mat_year,
        'effective_start_date': (
            rule.effective_start_date.isoformat() if rule.effective_start_date else None
        ),
        'effective_end_date': (
            rule.effective_end_date.isoformat() if rule.effective_end_date else None
        ),
    }


def _serialize_arrangement(
    arrangement: ContractArrangement,
    rules: list[PricingRule],
    materialized_year: Optional[int] = None,
) -> dict[str, Any]:
    return {
        'id': arrangement.id,
        'name': arrangement.name,
        'arrangement_type': arrangement.arrangement_type,
        'claim_type': arrangement.claim_type,
        'status': arrangement.status,
        'effective_start_date': (
            arrangement.effective_start_date.isoformat()
            if arrangement.effective_start_date else None
        ),
        'effective_end_date': (
            arrangement.effective_end_date.isoformat()
            if arrangement.effective_end_date else None
        ),
        'rules': [_serialize_rule(r, materialized_year) for r in rules],
    }


def _serialize_amendment(amendment: ContractAmendment) -> dict[str, Any]:
    return {
        'id': amendment.id,
        'amendment_number': amendment.amendment_number,
        'effective_date': amendment.effective_date.isoformat(),
        'description': amendment.description,
        'what_changed': amendment.what_changed,
        'status': amendment.status,
        'created_at': amendment.created_at.isoformat() if amendment.created_at else None,
    }


def _serialize_scope(scope: ContractScope) -> dict[str, Any]:
    return {
        'id': scope.id,
        'line_of_business': scope.line_of_business,
        'specialty_code': scope.specialty_code_id,
        'site_of_service': scope.site_of_service,
        'geo_id': scope.geo_id,
        'priority': scope.priority,
    }


def _serialize_product_scope(ps: ContractProductScope) -> dict[str, Any]:
    return {
        'id': ps.id,
        'lob_code': ps.lob_code,
        'product_id': ps.product_id,
        'effective_date': ps.effective_date.isoformat() if ps.effective_date else None,
        'termination_date': ps.termination_date.isoformat() if ps.termination_date else None,
    }


def _build_terms(
    contract: ProviderContract,
    scopes: list[ContractScope],
    product_scopes: list[ContractProductScope],
) -> list[str]:
    terms: list[str] = []
    if contract.line_of_business:
        terms.append(f'Line of business: {contract.line_of_business}')
    if contract.resolution_priority is not None:
        terms.append(f'Resolution priority: {contract.resolution_priority}')
    for ps in product_scopes:
        parts = []
        if ps.lob_code:
            parts.append(f'LOB {ps.lob_code}')
        if ps.product_id:
            parts.append(f'product #{ps.product_id}')
        label = ', '.join(parts) if parts else 'all products'
        terms.append(f'Product scope: {label}')
    for scope in scopes:
        parts = []
        if scope.line_of_business:
            parts.append(f'LOB {scope.line_of_business}')
        if scope.specialty_code_id:
            parts.append(f'specialty {scope.specialty_code_id}')
        if scope.site_of_service:
            parts.append(f'site {scope.site_of_service}')
        if parts:
            terms.append(f'Contract scope: {", ".join(parts)} (priority {scope.priority})')
    cap_count = ContractCapFloor.objects.filter(version__contract=contract).count()
    if cap_count:
        terms.append(f'{cap_count} cap/floor rule(s) configured')
    carve_count = ContractCarveout.objects.filter(version__contract=contract).count()
    if carve_count:
        terms.append(f'{carve_count} carve-out rule(s) configured')
    stop_count = ContractStopLossRule.objects.filter(contract=contract).count()
    if stop_count:
        terms.append(f'{stop_count} stop-loss rule(s) configured')
    outlier_count = ContractOutlierRule.objects.filter(contract=contract).count()
    if outlier_count:
        terms.append(f'{outlier_count} outlier rule(s) configured')
    if contract.network_id:
        terms.append(f'Network: {contract.network.network_name or contract.network_id}')
    return terms


def _origin_label(origin_type: str | None) -> str:
    labels = {
        'DIRECT': 'Direct',
        'LEASED': 'Leased',
        'DELEGATED': 'Delegated',
    }
    return labels.get(origin_type or '', origin_type or 'Unknown')


def _compose_abstract(
    contract: ProviderContract,
    parties: dict[str, Any],
    covered_entities: list[dict[str, Any]],
    arrangements: list[dict[str, Any]],
    product_scopes: list[ContractProductScope],
) -> str:
    payer = (parties.get('payer_org') or {}).get('name') or 'the payer'
    provider = (parties.get('provider_org') or {}).get('name') or 'the provider'
    network = (parties.get('network') or {}).get('network_name')
    lob = contract.line_of_business or (parties.get('network') or {}).get('line_of_business')

    scope_bits: list[str] = []
    if lob:
        scope_bits.append(lob.replace('_', ' ').title())
    if network:
        scope_bits.append(network)
    elif product_scopes:
        scope_bits.append('product-scoped')
    scope_phrase = ' '.join(scope_bits) if scope_bits else 'Healthcare'

    origin = _origin_label(contract.contract_origin_type)
    opening = f'{scope_phrase} agreement between {payer} and {provider}'
    if origin and origin != 'Unknown':
        opening += f' ({origin})'

    pricing_phrase = 'services priced per contract rules'
    for arr in arrangements:
        if arr.get('name') == '(ungrouped)':
            continue
        arr_type = (arr.get('arrangement_type') or '').replace('_', ' ')
        claim = arr.get('claim_type')
        methodology = None
        for rule in arr.get('rules') or []:
            if rule.get('methodology_code'):
                methodology = rule['methodology_code'].replace('_', ' ')
                break
        if methodology:
            pricing_phrase = f'{claim or "Services"} priced via {methodology}'
        elif arr_type:
            pricing_phrase = f'{claim or "Services"} via {arr_type}'
        break

    coverage_names: list[str] = []
    for entity in covered_entities:
        name = entity.get('name')
        if not name:
            continue
        if entity.get('is_primary'):
            coverage_names.insert(0, name)
        else:
            coverage_names.append(name)
    coverage_phrase = ''
    if coverage_names:
        if len(coverage_names) == 1:
            coverage_phrase = f'Covers {coverage_names[0]}.'
        else:
            coverage_phrase = f'Covers {coverage_names[0]} and {", ".join(coverage_names[1:])}.'

    start = contract.effective_start_date.isoformat()
    end = (
        contract.effective_end_date.isoformat()
        if contract.effective_end_date else None
    )
    date_phrase = f'Effective {start}'
    if end:
        date_phrase += f' – {end}'
    date_phrase += f', {contract.status.lower() if contract.status else "unknown status"}.'

    return f'{opening}. {pricing_phrase.capitalize()}. {coverage_phrase} {date_phrase}'.replace('  ', ' ').strip()


class ContractSummaryService:
    """Assemble the full layered contract view as plain dicts (no queryset leakage)."""

    @staticmethod
    def build(contract_id: int) -> dict[str, Any]:
        try:
            contract = ProviderContract.objects.select_related(
                'provider_org',
                'provider_org__parent_org',
                'network',
                'payer_org',
            ).get(pk=contract_id)
        except ProviderContract.DoesNotExist as exc:
            raise ObjectDoesNotExist(f'Contract {contract_id} not found') from exc

        documents = list(
            ContractDocument.objects.filter(contract=contract).order_by('-uploaded_at')
        )
        covered_entities = list(
            ContractCoveredEntity.objects.filter(contract=contract)
            .select_related('organization', 'facility', 'provider')
            .order_by('-is_primary', 'entity_type', 'id')
        )
        arrangements = list(
            ContractArrangement.objects.filter(contract=contract).order_by('name')
        )
        rules_by_arrangement: dict[int, list[PricingRule]] = {a.id: [] for a in arrangements}
        ungrouped_rules: list[PricingRule] = []
        for rule in PricingRule.objects.filter(contract=contract).select_related(
            'rate_basis__schedule',
            'contract',
            'version',
        ).order_by('rule_id'):
            if rule.arrangement_id and rule.arrangement_id in rules_by_arrangement:
                rules_by_arrangement[rule.arrangement_id].append(rule)
            else:
                ungrouped_rules.append(rule)

        materialized_year = date.today().year

        arrangement_payloads = [
            _serialize_arrangement(a, rules_by_arrangement.get(a.id, []), materialized_year)
            for a in arrangements
        ]
        if ungrouped_rules:
            arrangement_payloads.append({
                'id': None,
                'name': '(ungrouped)',
                'arrangement_type': None,
                'claim_type': None,
                'status': None,
                'effective_start_date': None,
                'effective_end_date': None,
                'rules': [_serialize_rule(r, materialized_year) for r in ungrouped_rules],
            })

        amendments = list(
            ContractAmendment.objects.filter(contract=contract).order_by('-effective_date')
        )
        scopes = list(ContractScope.objects.filter(contract=contract).order_by('priority'))
        product_scopes = list(
            ContractProductScope.objects.filter(contract=contract).order_by('id')
        )

        parties = {
            'payer_org': _serialize_payer_org(contract.payer_org),
            'provider_org': _serialize_provider_org(contract.provider_org),
            'network': _serialize_network(contract.network),
        }
        covered_payloads = [_serialize_covered_entity(e) for e in covered_entities]
        terms = _build_terms(contract, scopes, product_scopes)
        abstract = _compose_abstract(
            contract,
            parties,
            covered_payloads,
            arrangement_payloads,
            product_scopes,
        )

        return {
            'abstract': abstract,
            'header': {
                'contract_id': contract.contract_id,
                'contract_name': contract.contract_name,
                'legacy_contract_number': contract.legacy_contract_number,
                'status': contract.status,
                'contract_origin_type': contract.contract_origin_type,
                'effective_start_date': contract.effective_start_date.isoformat(),
                'effective_end_date': (
                    contract.effective_end_date.isoformat()
                    if contract.effective_end_date else None
                ),
            },
            'contract_id': contract.contract_id,
            'contract_name': contract.contract_name,
            'legacy_contract_number': contract.legacy_contract_number,
            'status': contract.status,
            'effective_start_date': contract.effective_start_date.isoformat(),
            'effective_end_date': (
                contract.effective_end_date.isoformat() if contract.effective_end_date else None
            ),
            'contract_origin_type': contract.contract_origin_type,
            'line_of_business': contract.line_of_business,
            'parties': parties,
            'documents': [_serialize_document(d) for d in documents],
            'covered_entities': covered_payloads,
            'arrangements': arrangement_payloads,
            'amendments': [_serialize_amendment(a) for a in amendments],
            'terms': terms,
            'materialized_year': materialized_year,
            'scopes': [_serialize_scope(s) for s in scopes],
            'product_scopes': [_serialize_product_scope(ps) for ps in product_scopes],
        }
