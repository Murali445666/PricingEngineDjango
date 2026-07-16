"""
Remove directory entities not referenced by ACTIVE contracts (safe FK order).

Destructive — back up first. Defaults to dry-run; pass --apply to delete.

Usage:
  python manage.py purge_orphan_entities              # dry-run (default)
  python manage.py purge_orphan_entities --apply      # backup + delete + verify
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.services.orphan_entity_purge import (
    SAMPLE_DEFAULT,
    build_purge_plan,
    execute_purge,
)


class Command(BaseCommand):
    help = (
        'Remove orphan provider/member/product directory rows not needed by ACTIVE '
        'contracts. Dry-run by default; requires --apply to delete.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Perform backup + delete (default is dry-run only).',
        )
        parser.add_argument(
            '--sample',
            type=int,
            default=SAMPLE_DEFAULT,
            help=f'Number of sample labels per entity type in dry-run (default {SAMPLE_DEFAULT}).',
        )
        parser.add_argument(
            '--backup-dir',
            type=str,
            default=None,
            help='Directory for dumpdata backup (default: <BASE_DIR>/backups).',
        )

    def handle(self, *args, **options):
        apply = options['apply']
        sample_size = options['sample']
        base_dir = Path(settings.BASE_DIR)
        backup_dir = Path(options['backup_dir'] or (base_dir / 'backups'))

        plan = build_purge_plan(sample_size=sample_size)
        protected = plan.protected

        self.stdout.write('Protected (ACTIVE contract subgraph + archive anchors):')
        self.stdout.write(f"  provider_organizations: {len(protected.org_ids)}")
        self.stdout.write(f"  providers:            {len(protected.provider_ids)}")
        self.stdout.write(f"  facilities:           {len(protected.facility_ids)}")
        self.stdout.write(f"  members:              {len(protected.member_ids)}")
        self.stdout.write(f"  enrollments:          {len(protected.enrollment_ids)}")
        self.stdout.write(f"  products:             {len(protected.product_ids)}")
        self.stdout.write(f"  payer_organizations:  {len(protected.payer_org_ids)}")
        self.stdout.write(f"  networks (products):  {len(protected.network_ids)}")
        self.stdout.write(f"  payer_networks:       {len(protected.payer_network_ids)}")
        self.stdout.write(f"  lines_of_business:    {len(protected.lob_ids)}")
        self.stdout.write('')

        self.stdout.write('Entity totals vs. would delete:')
        for key in (
            'providers', 'facilities', 'members', 'enrollments',
            'provider_affiliations', 'provider_network_participations',
            'facility_network_participations', 'products', 'product_network_configs',
            'networks', 'payer_organizations', 'lines_of_business',
            'provider_organizations', 'payer_networks',
        ):
            total = plan.totals.get(key, 0)
            to_delete = plan.delete_counts.get(key, 0)
            kept = total - to_delete
            self.stdout.write(
                f"  {key:32} total={total:5}  protected~={kept:5}  to_delete={to_delete:5}"
            )

        for entity_type, labels in plan.samples.items():
            if labels:
                self.stdout.write('')
                self.stdout.write(f"Sample {entity_type} to delete: {', '.join(labels)}")

        if not apply:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Dry run — no rows deleted. Re-run with --apply to backup and purge.'
            ))
            return

        if sum(plan.delete_counts.values()) == 0:
            self.stdout.write(self.style.SUCCESS('Nothing to delete.'))
            return

        self.stdout.write('')
        self.stdout.write('Applying purge (backup → delete in transaction)...')
        try:
            result = execute_purge(plan, backup_dir=backup_dir)
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f'Backup written: {result.backup_path}'))
        self.stdout.write('Deleted:')
        for key, count in result.deleted.items():
            if count:
                self.stdout.write(f'  {key}: {count}')

        v = result.verification
        self.stdout.write('')
        self.stdout.write('Post-purge verification:')
        self.stdout.write(f"  P1 (no rendering):  ${v['p1_allowed']}  rule {v['p1_rule_id']}")
        self.stdout.write(f"  P5 (Chen):          ${v['p5_allowed']}  rule {v['p5_rule_id']}")
        self.stdout.write(
            f"  validate-contract/217: {v['validation_errors']} errors, "
            f"{v['validation_warnings']} warnings"
        )
        self.stdout.write(
            f"  providers remaining: {v['provider_count']}  members remaining: {v['member_count']}"
        )
        self.stdout.write(f"  ACTIVE contracts: {v['active_contracts']}")

        if v['p1_allowed'] != '108.12' or v['p5_allowed'] != '116.44':
            raise CommandError(
                f"Pricing verification failed: P1={v['p1_allowed']} P5={v['p5_allowed']}"
            )
        if v['validation_errors'] or v['validation_warnings']:
            raise CommandError(
                f"Contract 217 validation not clean: "
                f"{v['validation_errors']} errors, {v['validation_warnings']} warnings"
            )

        self.stdout.write(self.style.SUCCESS('\nPurge complete.'))
