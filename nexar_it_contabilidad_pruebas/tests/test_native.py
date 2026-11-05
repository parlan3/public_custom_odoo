import io
import zipfile

from odoo import Command, fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import SQL
from .test_security import TestCircuitSecurity


class TestCdpNative(TestCircuitSecurity):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.circuit._initialize_standard()
        cls.partner = cls.env['res.partner'].create({'name': 'CDP QA Partner'})
        cls.conventional = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'CDP QA conventional accountant', 'login': 'cdp_qa_conventional',
            'company_id': cls.company.id, 'company_ids': [Command.set(cls.company.ids)],
            'group_ids': [Command.set([cls.env.ref('base.group_user').id,
                                       cls.env.ref('account.group_account_user').id])],
        })

    def invoice(self, kind):
        journal_type = 'sale' if kind == 'out_invoice' else 'purchase'
        journal = self.env['account.journal'].search([
            ('cdp_circuit_id', '=', self.circuit.id), ('type', '=', journal_type),
        ], limit=1)
        return self.env['account.move'].with_user(self.owner).with_context(cdp_entry=True).create({
            'move_type': kind, 'journal_id': journal.id,
            'partner_id': self.partner.id, 'invoice_date': fields.Date.today(),
            'invoice_line_ids': [Command.create({'name': 'CDP QA', 'quantity': 1, 'price_unit': 100})],
        })

    def test_customer_and_vendor_payment(self):
        for kind in ('out_invoice', 'in_invoice'):
            invoice = self.invoice(kind)
            invoice.action_post()
            self.assertEqual(invoice.amount_total, 100)
            self.assertTrue(all(line.account_id.cdp_circuit_id == self.circuit for line in invoice.line_ids))
            journal = self.env['account.journal'].search([
                ('cdp_circuit_id', '=', self.circuit.id), ('type', '=', 'cash'),
            ], limit=1)
            wizard = self.env['account.payment.register'].with_user(self.owner).with_context(
                active_model='account.move', active_ids=invoice.ids,
            ).create({'journal_id': journal.id, 'amount': 100, 'payment_date': fields.Date.today()})
            wizard.action_create_payments()
            invoice.invalidate_recordset()
            self.assertEqual(invoice.amount_residual, 0)
            self.assertEqual(invoice.payment_state, 'paid')
            with self.assertRaises(AccessError), self.cr.savepoint():
                invoice.with_user(self.other).read(['amount_total'])

    def test_report_scopes_and_ordinary_user(self):
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        report = self.env.ref('account_reports.general_ledger_report').with_user(self.owner)
        for scope, included in [('fiscal', False), ('cdp', True), ('both', True)]:
            scoped = report.with_context(cdp_report_scope=scope)
            options = scoped.get_options({})
            domain = scoped._get_options_domain(options, None)
            found = self.env['account.move.line'].with_user(self.owner).search(domain)
            self.assertEqual(bool(found & invoice.line_ids), included)
        self.assertFalse(self.env['account.move'].with_user(self.other).search([('id','=',invoice.id)]))

    def test_cross_circuit_account_rejected(self):
        invoice = self.invoice('out_invoice')
        account = self.env['account.account'].search([
            ('company_ids','in',self.company.ids), ('cdp_circuit_id','=',False),
            ('account_type','=','income'),
        ], limit=1)
        if not account:
            self.skipTest('No fiscal income account in this test database')
        with self.assertRaises(ValidationError), self.cr.savepoint():
            invoice.invoice_line_ids.write({'account_id': account.id})

    def test_public_sharing_rejected(self):
        invoice = self.invoice('out_invoice')
        with self.assertRaises(AccessError):
            invoice._portal_ensure_token()

    def test_classification_cannot_be_forged(self):
        invoice = self.invoice('out_invoice')
        for record in (invoice, invoice.line_ids):
            for field in ('cdp_circuit_id', 'cdp_user_id'):
                with self.assertRaises(AccessError), self.cr.savepoint():
                    record.write({field: False})

    def test_conventional_user_direct_aggregate_and_export_denied(self):
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        rows = invoice.line_ids.with_user(self.conventional)
        self.assertFalse(rows.search([('id', 'in', rows.ids)]))
        self.assertFalse(rows._read_group([('id', 'in', rows.ids)], ['account_id'], ['balance:sum']))
        with self.assertRaises(AccessError), self.cr.savepoint():
            rows.read(['balance'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            rows.export_data(['balance'])
        analysis = self.env['account.invoice.report'].with_user(self.conventional)
        self.assertFalse(analysis.search([('move_id', '=', invoice.id)]))
        self.assertFalse(analysis.sudo()._read_group([('move_id', '=', invoice.id)], ['partner_id'], ['price_subtotal:sum']))

    def test_normal_partner_totals_and_search_exclude_cdp(self):
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        owner_partner = self.partner.with_user(self.owner)
        self.assertEqual(owner_partner.credit, 100)
        normal_partner = self.partner.with_user(self.conventional)
        self.assertEqual(normal_partner.credit, 0)
        self.assertEqual(normal_partner.total_invoiced, 0)
        self.assertFalse(normal_partner.search([('id', '=', self.partner.id), ('credit', '>', 0)]))

    def test_sudo_and_bypass_search_still_isolate_conventional_user(self):
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        lines = self.env['account.move.line'].with_user(self.conventional).sudo()
        query = lines._search([('id', 'in', invoice.line_ids.ids)], bypass_access=True)
        self.assertFalse(self.env.execute_query(query.select(SQL.identifier('account_move_line', 'id'))))

    def test_forged_report_filters_do_not_grant_access(self):
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        report = self.env.ref('account_reports.general_ledger_report').with_user(self.conventional)
        for elevated in (False, True):
            report = report.sudo(elevated).with_context(cdp_report_scope='both')
            options = report.get_options({'cdp_scope': 'both'})
            self.assertEqual(options['cdp_scope'], 'fiscal')
            options['cdp_scope'] = 'both'
            options['forced_domain'] = [('id', 'in', invoice.line_ids.ids)]
            options['journals'] = [{'id': invoice.journal_id.id, 'model': 'account.journal',
                                    'name': 'Injected journal', 'selected': True}]
            query = report._get_report_query(options, None)
            self.assertFalse(self.env.execute_query(query.select(SQL.identifier('account_move_line', 'id'))))

    def test_normal_major_and_xlsx_totals_do_not_change(self):
        report = self.env.ref('account_reports.general_ledger_report').with_user(self.conventional)
        options = report.get_options({})
        before_lines = report.get_report_information(options)['lines']
        before_xlsx = report.export_to_xlsx(options)['file_content']
        invoice = self.invoice('out_invoice')
        invoice.action_post()
        self.assertEqual(before_lines, report.get_report_information(options)['lines'])
        after_xlsx = report.export_to_xlsx(options)['file_content']
        # Workbook metadata contains generation dates. Compare data and labels.
        def workbook_payload(blob):
            with zipfile.ZipFile(io.BytesIO(blob)) as archive:
                return {name: archive.read(name) for name in archive.namelist()
                        if name.startswith('xl/worksheets/') or name == 'xl/sharedStrings.xml'}
        self.assertEqual(workbook_payload(before_xlsx), workbook_payload(after_xlsx))
