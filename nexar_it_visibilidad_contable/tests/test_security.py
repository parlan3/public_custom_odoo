from odoo import Command
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestCircuitSecurity(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(su=True)
        cls.company = cls.company_data['company']
        cls.public_journal = cls.company_data['default_journal_misc']
        cls.private_journal = cls.env['account.journal'].create({
            'name': 'Prueba diario restringido', 'code': 'XSEC', 'type': 'general',
            'company_id': cls.company.id, 'restricted_accounting': True})
        cls.debit_account = cls.company_data['default_account_expense']
        cls.credit_account = cls.company_data['default_account_revenue']
        cls.private_account = cls.env['account.account'].create({
            'name': 'Prueba cuenta restringida', 'code': '999998SEC',
            'account_type': 'expense', 'company_ids': [Command.set(cls.company.ids)],
            'restricted_accounting': True})
        cls.outsider = cls._user('circuit_test_none', ['account.group_account_user'])
        cls.reader = cls._user('circuit_test_read', ['nexar_it_visibilidad_contable.group_reader'])
        cls.operator = cls._user('circuit_test_operate', ['nexar_it_visibilidad_contable.group_operator'])
        # Deliberately give this reader native write access: custom restrictions
        # must still win over existing accounting grants on restricted entries.
        cls.reader_writer = cls._user('circuit_test_read_write', [
            'account.group_account_user', 'nexar_it_visibilidad_contable.group_reader'])
        cls.admin_hidden = cls._user('circuit_test_admin', [
            'base.group_system', 'account.group_account_manager'])
        cls.private_move = cls.env['account.move'].create(cls._move_values(cls.private_journal))
        cls.public_move = cls.env['account.move'].create(cls._move_values(cls.public_journal))

    @classmethod
    def _user(cls, login, groups):
        return cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': login, 'login': login, 'company_id': cls.company.id,
            'company_ids': [Command.set(cls.company.ids)],
            'group_ids': [Command.set([cls.env.ref('base.group_user').id] + [cls.env.ref(g).id for g in groups])]})

    @classmethod
    def _move_values(cls, journal, account=None):
        return {'journal_id': journal.id, 'company_id': cls.company.id,
                'line_ids': [Command.create({'name': 'Debe', 'account_id': (account or cls.debit_account).id, 'debit': 10}),
                             Command.create({'name': 'Haber', 'account_id': cls.credit_account.id, 'credit': 10})]}

    def test_denied_search_direct_read_and_export_including_admin(self):
        for user in (self.outsider, self.admin_hidden):
            for record in (self.private_journal, self.private_account, self.private_move, self.private_move.line_ids):
                target = record.with_user(user)
                self.assertFalse(target.search([('id', 'in', record.ids)]))
                with self.assertRaises(AccessError), self.cr.savepoint():
                    target.read(['display_name'])
                with self.assertRaises(AccessError), self.cr.savepoint():
                    target.export_data(['display_name'])
            self.assertTrue(self.public_move.with_user(user).read(['name']))

    def test_reader_cannot_mutate_even_with_native_write_grants(self):
        for user in (self.reader, self.reader_writer):
            self.assertTrue(self.private_move.with_user(user).read(['name']))
            with self.assertRaises(AccessError), self.cr.savepoint():
                self.private_move.with_user(user).write({'ref': 'No permitido'})
            with self.assertRaises(AccessError), self.cr.savepoint():
                self.private_move.with_user(user).unlink()
            with self.assertRaises(AccessError), self.cr.savepoint():
                self.env['account.move'].with_user(user).create(self._move_values(self.private_journal))
            with self.assertRaises(AccessError), self.cr.savepoint():
                self.public_move.with_user(user).write({'journal_id': self.private_journal.id})

    def test_operator_and_restricted_account_in_ordinary_journal(self):
        entry = self.env['account.move'].with_user(self.operator).create(self._move_values(self.private_journal))
        entry.write({'ref': 'Operación permitida'})
        self.assertEqual(entry.ref, 'Operación permitida')
        entry2 = self.env['account.move'].with_user(self.operator).create(self._move_values(self.public_journal, self.private_account))
        self.assertTrue(entry2.restricted_accounting)
        with self.assertRaises(AccessError), self.cr.savepoint():
            entry2.with_user(self.outsider).read(['name'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            entry.with_user(self.operator).write({'restricted_accounting': False})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.private_journal.with_user(self.operator).write({'restricted_accounting': False})

    def test_links_created_after_warming_rule_cache_are_hidden(self):
        Attach = self.env['ir.attachment']
        Attach.with_user(self.outsider).search([('res_model', '=', 'account.move')])
        attachment = Attach.create({'name': 'Privado.txt', 'raw': b'confidencial',
                                    'res_model': 'account.move', 'res_id': self.private_move.id})
        self.assertFalse(Attach.with_user(self.outsider).search([('id', '=', attachment.id)]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            attachment.with_user(self.outsider).read(['raw'])
        self.assertTrue(attachment.with_user(self.reader).read(['name']))
        with self.assertRaises(ValidationError), self.cr.savepoint():
            attachment.write({'public': True})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            attachment.write({'access_token': 'prohibido'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.private_move._portal_ensure_token()

    def test_boolean_link_search_matches_computed_classification(self):
        Attach = self.env['ir.attachment']
        ordinary = Attach.create({'name': 'Público de prueba.txt', 'raw': b'ordinary',
            'res_model': 'account.move', 'res_id': self.public_move.id})
        private = Attach.create({'name': 'Restringido de prueba.txt', 'raw': b'private',
            'res_model': 'account.move', 'res_id': self.private_move.id})
        candidates = ordinary | private
        for operator, value, expected in [
            ('=', True, private), ('=', False, ordinary),
            ('in', [True], private), ('not in', [True], ordinary),
            ('in', [False], ordinary), ('not in', [False], private),
            ('in', [], Attach.browse()), ('not in', [], candidates),
            ('in', [True, False], candidates), ('not in', [True, False], Attach.browse()),
        ]:
            result = Attach.search([('id', 'in', candidates.ids), ('restricted_accounting', operator, value)])
            self.assertEqual(set(result.ids), set(expected.ids))

    def test_reclassification_after_existing_attachment(self):
        attachment = self.env['ir.attachment'].create({'name': 'Anterior.txt', 'raw': b'x',
            'res_model': 'account.move', 'res_id': self.public_move.id})
        self.assertTrue(attachment.with_user(self.outsider).read(['name']))
        self.public_move.write({'journal_id': self.private_journal.id})
        with self.assertRaises(AccessError), self.cr.savepoint():
            attachment.with_user(self.outsider).read(['name'])

    def test_no_notifications_to_followers(self):
        result = self.private_move._notify_thread(self.env['mail.message'])
        self.assertEqual(result, [])

    def test_user_selection_grants_and_revokes(self):
        self.outsider.restricted_accounting_access = 'read'
        self.assertTrue(self.private_move.with_user(self.outsider).read(['name']))
        self.outsider.restricted_accounting_access = 'operate'
        self.private_move.with_user(self.outsider).write({'ref': 'Temporal'})
        self.outsider.restricted_accounting_access = 'none'
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.private_move.with_user(self.outsider).read(['name'])

    def test_invoice_analysis_sql_scope(self):
        sql = self.env['account.invoice.report'].with_user(self.outsider)._where()
        self.assertIn('restricted_accounting', sql.code)
        for user in (self.reader, self.operator):
            sql = self.env['account.invoice.report'].with_user(user)._where()
            self.assertNotIn('restricted_accounting', sql.code)

    def test_general_ledger_domain_respects_native_filters(self):
        report = self.env.ref('account_reports.general_ledger_report')
        for user, visible in ((self.outsider, False), (self.reader, True), (self.operator, True)):
            scoped_report = report.with_user(user).with_context(allowed_company_ids=self.company.ids)
            options = scoped_report.get_options({})
            domain = scoped_report._get_options_domain(options, 'strict_range')
            text = str(domain)
            self.assertEqual('restricted_accounting' in text, not visible)

    def test_readonly_line_edit_and_reparent_are_denied(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.private_move.line_ids[:1].with_user(self.reader_writer).write({'name': 'Cambio no permitido'})
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.public_move.line_ids[:1].with_user(self.reader_writer).write({'account_id': self.private_account.id})

    def test_native_account_suggestions_do_not_expose_private_accounts(self):
        move = self.env['account.move'].create(self._move_values(self.private_journal, self.private_account))
        move.line_ids.write({'partner_id': self.partner_a.id})
        accounts = self.env['account.account'].with_user(self.outsider).with_context(
            partner_id=self.partner_a.id, move_type='in_invoice')
        suggestions = accounts.name_search()
        self.assertNotIn(self.private_account.id, [row[0] for row in suggestions])

    def test_native_company_rules_still_apply(self):
        company = self.env['res.company'].create({'name': 'Otra empresa privada'})
        journal = self.env['account.journal'].create({'name': 'Otra empresa', 'code': 'OTHER',
            'type': 'general', 'company_id': company.id, 'restricted_accounting': True})
        with self.assertRaises(AccessError), self.cr.savepoint():
            journal.with_user(self.operator).with_context(allowed_company_ids=self.company.ids).read(['name'])
