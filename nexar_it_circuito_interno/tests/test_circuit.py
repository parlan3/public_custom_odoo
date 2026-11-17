from odoo import Command, fields, SUPERUSER_ID
from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import TransactionCase, tagged
from odoo.tools import SQL


@tagged('post_install', '-at_install')
class TestInternalCircuit(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        admin = cls.env['res.company'].with_user(SUPERUSER_ID)
        ars = cls.env.ref('base.ARS')
        usd = cls.env.ref('base.USD')
        (ars | usd).active = True
        cls.companies = admin.create([
            {'name': 'NI QA ' + str(i), 'currency_id': ars.id,
             'country_id': cls.env.ref('base.ar').id}
            for i in range(4)
        ])
        cls.owner = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'NI QA titular', 'login': 'ni_qa_owner',
            'company_id': cls.companies[0].id, 'company_ids': [Command.set(cls.companies.ids)],
            'group_ids': [Command.set([cls.env.ref('base.group_user').id,
                                      cls.env.ref('base.group_multi_company').id,
                                      cls.env.ref('nexar_it_circuito_interno.group_operator').id])],
        })
        cls.other = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'NI QA contador habitual', 'login': 'ni_qa_other',
            'company_id': cls.companies[0].id, 'company_ids': [Command.set(cls.companies.ids)],
            'group_ids': [Command.set([cls.env.ref('base.group_user').id,
                                      cls.env.ref('base.group_multi_company').id,
                                      cls.env.ref('account.group_account_user').id])],
        })
        cls.circuits = cls.env['nexar.internal.circuit'].with_user(SUPERUSER_ID)
        for company in cls.companies:
            circuit = cls.circuits.create({'name': company.name, 'company_id': company.id,
                                           'user_id': cls.owner.id})
            circuit._initialize()
            cls.circuits |= circuit
            cls.env['res.currency.rate'].create([
                {'currency_id': usd.id, 'company_id': company.id, 'name': '2026-11-01', 'rate': 0.001},
                {'currency_id': usd.id, 'company_id': company.id, 'name': '2026-11-02', 'rate': 0.0008},
            ])
        cls.partner = cls.env['res.partner'].create({'name': 'NI QA cliente proveedor'})
        cls.ars, cls.usd = ars, usd

    def invoice(self, circuit, kind='out_invoice', currency=None):
        owner_env = self.env['account.move'].with_user(self.owner).with_context(
            allowed_company_ids=circuit.company_id.ids)
        return owner_env.create({
            'move_type': kind,
            'journal_id': circuit._journal('INTV' if kind == 'out_invoice' else 'INTC').id,
            'partner_id': self.partner.id, 'currency_id': (currency or self.ars).id,
            'invoice_date': '2026-11-01', 'date': '2026-11-01',
            'invoice_line_ids': [Command.create({
                'name': 'QA interno', 'quantity': 1, 'price_unit': 100,
            })],
        })

    def pay(self, invoice, circuit, currency):
        wizard = self.env['account.payment.register'].with_user(self.owner).with_context(
            allowed_company_ids=circuit.company_id.ids,
            active_model='account.move', active_ids=invoice.ids,
        ).create({
            'journal_id': circuit._journal('INUSD' if currency == self.usd else 'INARS').id,
            'payment_date': '2026-11-02', 'amount': 100,
        })
        wizard.action_create_payments()
        invoice.invalidate_recordset()
        self.assertEqual(invoice.amount_residual, 0)
        self.assertEqual(invoice.payment_state, 'paid')

    def test_sale_purchase_ars_usd_four_companies(self):
        for circuit in self.circuits:
            for kind in ('out_invoice', 'in_invoice'):
                for currency in (self.ars, self.usd):
                    with self.subTest(company=circuit.company_id.name, kind=kind, currency=currency.name):
                        invoice = self.invoice(circuit, kind, currency)
                        invoice.action_post()
                        self.assertEqual(invoice.amount_total, 100)
                        self.assertFalse(invoice.line_ids.tax_ids)
                        self.assertTrue(all(l.account_id.ni_circuit_id == circuit for l in invoice.line_ids))
                        self.pay(invoice, circuit, currency)
                        fx = self.env['account.move'].with_user(SUPERUSER_ID).search([
                            ('journal_id', '=', circuit._journal('INTFX').id), ('state', '=', 'posted')])
                        if currency == self.usd:
                            self.assertTrue(fx)
                            self.assertTrue(all(l.account_id.ni_circuit_id == circuit for l in fx.line_ids))

    def test_defaults_do_not_read_partner_accounts(self):
        circuit = self.circuits[0]
        ordinary = self.env['account.account'].with_user(SUPERUSER_ID).with_company(circuit.company_id).create({
            'name': 'NI QA cuenta habitual', 'code': 'QAORD001', 'account_type': 'asset_receivable',
            'company_ids': [Command.set(circuit.company_id.ids)], 'reconcile': True})
        self.partner.with_company(circuit.company_id).property_account_receivable_id = ordinary
        invoice = self.invoice(circuit)
        self.assertEqual(invoice.line_ids.filtered(lambda l: l.display_type == 'payment_term').account_id,
                         circuit._account('receivable'))
        self.assertEqual(self.partner.with_company(circuit.company_id).property_account_receivable_id, ordinary)

    def test_private_read_export_aggregate_and_sudo(self):
        invoice = self.invoice(self.circuits[0])
        invoice.action_post()
        for model, records in [('account.move', invoice), ('account.move.line', invoice.line_ids),
                               ('account.account', invoice.line_ids.account_id),
                               ('account.journal', invoice.journal_id)]:
            hidden = records.with_user(self.other)
            self.assertFalse(hidden.search([('id', 'in', records.ids)]))
            self.assertFalse(hidden.sudo().search([('id', 'in', records.ids)]))
            with self.assertRaises(AccessError), self.cr.savepoint():
                hidden.read(['display_name'])
            with self.assertRaises(AccessError), self.cr.savepoint():
                hidden.export_data(['display_name'])
        self.assertFalse(self.env['account.invoice.report'].with_user(self.other).sudo().search([
            ('move_id', '=', invoice.id)]))
        partner = self.partner.with_user(self.other).with_company(self.circuits[0].company_id)
        self.assertEqual(partner.credit, 0)
        self.assertEqual(partner.total_invoiced, 0)

    def test_cross_company_and_classification(self):
        a, b = self.circuits[:2]
        invoice = self.invoice(a)
        for vals in [{'ni_circuit_id': b.id}, {'journal_id': b._journal('INTV').id}]:
            with self.assertRaises((AccessError, ValidationError)), self.cr.savepoint():
                invoice.write(vals)
        with self.assertRaises((AccessError, ValidationError)), self.cr.savepoint():
            invoice.invoice_line_ids.write({'account_id': b._account('income').id})
        with self.assertRaises(AccessError):
            invoice._portal_ensure_token()

    def test_setup_idempotent(self):
        circuit = self.circuits[0]
        accounts, journals = circuit.account_ids.ids, circuit.journal_ids.ids
        circuit._initialize()
        self.assertEqual(circuit.account_ids.ids, accounts)
        self.assertEqual(circuit.journal_ids.ids, journals)

    def test_reports_exclude_private_for_other_user(self):
        circuit = self.circuits[0]
        report = self.env.ref('account_reports.general_ledger_report').with_user(self.other).with_context(
            allowed_company_ids=circuit.company_id.ids)
        options = report.get_options({})
        options['date'] = dict(options.get('date', {}),
                               date_from='2026-11-01', date_to='2026-11-30', mode='range')
        before = report.get_report_information(options)['lines']
        invoice = self.invoice(circuit)
        invoice.action_post()
        self.assertEqual(before, report.get_report_information(options)['lines'])
        options['forced_domain'] = [('id', 'in', invoice.line_ids.ids)]
        for elevated in (False, True):
            query = report.sudo(elevated)._get_report_query(options, None)
            found = self.env.execute_query(query.select(SQL.identifier('account_move_line', 'id')))
            self.assertFalse(set(row[0] for row in found) & set(invoice.line_ids.ids))

    def test_owner_report_and_refund(self):
        circuit = self.circuits[0]
        invoice = self.invoice(circuit)
        invoice.action_post()
        refund = invoice._reverse_moves([{'date': fields.Date.to_date('2026-11-02')}], cancel=False)
        refund.action_post()
        self.assertTrue(all(l.account_id.ni_circuit_id == circuit for l in refund.line_ids))
        report = self.env.ref('account_reports.general_ledger_report').with_user(self.owner).with_context(
            allowed_company_ids=circuit.company_id.ids)
        options = report.get_options({})
        options['date'] = dict(options.get('date', {}),
                               date_from='2026-11-01', date_to='2026-11-30', mode='range')
        query = report._get_report_query(options, None)
        found = self.env.execute_query(query.select(SQL.identifier('account_move_line', 'id')))
        self.assertTrue(set(row[0] for row in found) & set(invoice.line_ids.ids))


    def test_attachment_privacy_after_new_record(self):
        # Warm rule caches before creation to detect stale visibility domains.
        attachments = self.env['ir.attachment'].with_user(self.other)
        attachments.search_count([])
        invoice = self.invoice(self.circuits[0])
        attachment = self.env['ir.attachment'].with_user(self.owner).create({
            'name': 'QA interno.txt', 'type': 'binary', 'datas': 'UUE=',
            'res_model': 'account.move', 'res_id': invoice.id,
        })
        self.assertFalse(attachments.search([('id', '=', attachment.id)]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            attachment.with_user(self.other).read(['datas'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            attachment.write({'public': True})


    def test_native_accounting_remains_operational(self):
        company = self.companies[0]
        admin_accounts = self.env['account.account'].with_user(SUPERUSER_ID).with_company(company)
        income = admin_accounts.create({
            'name': 'NI QA ingreso habitual', 'code': 'QAORD002', 'account_type': 'income',
            'company_ids': [Command.set(company.ids)]})
        receivable = admin_accounts.create({
            'name': 'NI QA cliente habitual', 'code': 'QAORD003', 'account_type': 'asset_receivable',
            'company_ids': [Command.set(company.ids)], 'reconcile': True})
        journal = self.env['account.journal'].with_user(SUPERUSER_ID).create({
            'name': 'NI QA diario habitual', 'code': 'QAORD', 'type': 'sale',
            'company_id': company.id, 'default_account_id': income.id,
            'l10n_latam_use_documents': False})
        self.partner.with_company(company).property_account_receivable_id = receivable
        invoice = self.env['account.move'].with_user(self.other).with_context(
            allowed_company_ids=company.ids).create({
                'move_type': 'out_invoice', 'journal_id': journal.id, 'partner_id': self.partner.id,
                'invoice_date': '2026-11-01',
                'invoice_line_ids': [Command.create({
                    'name': 'QA habitual', 'account_id': income.id, 'price_unit': 100,
                    'quantity': 1, 'tax_ids': [Command.clear()],
                })],
            })
        invoice.action_post()
        self.assertFalse(invoice.ni_circuit_id)
        self.assertEqual(invoice.amount_total, 100)
        self.assertFalse(invoice.with_user(self.owner).search([('id', '=', invoice.id)]))
        with self.assertRaises((AccessError, ValidationError)), self.cr.savepoint():
            invoice.invoice_line_ids.write({'account_id': self.circuits[0]._account('income').id})


    def test_payment_method_temporary_detach(self):
        circuit = self.circuits[0]
        journal = circuit._journal('INARS')
        method = journal.inbound_payment_method_line_ids[:1]
        self.assertTrue(method)
        self.assertEqual(method.payment_account_id.ni_circuit_id, circuit)
        # Mirror account.journal's One2many recompute, which clears the inverse
        # before removing or reassigning a payment method.
        method.write({'journal_id': False})
        self.assertFalse(method.journal_id)
        method.write({'journal_id': journal.id})
        self.assertEqual(method.journal_id, journal)

    def test_payment_method_wrong_circuit_still_rejected(self):
        circuit, other = self.circuits[:2]
        method = circuit._journal('INARS').inbound_payment_method_line_ids[:1].with_user(self.owner)
        with self.assertRaises((AccessError, ValidationError)), self.cr.savepoint():
            method.write({'payment_account_id': other._account('cash_ars').id})
