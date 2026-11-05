from odoo import Command
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import AccessError, ValidationError, UserError


@tagged('post_install', '-at_install')
class TestCircuitSecurity(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        group = cls.env.ref('nexar_it_contabilidad_pruebas.group_operator')
        cls.owner = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Circuit owner', 'login': 'nexar_test_owner',
            'company_id': cls.company.id, 'company_ids': [Command.set(cls.company.ids)],
            'group_ids': [Command.set([group.id, cls.env.ref('base.group_user').id,
                                       cls.env.ref('account.group_account_readonly').id])],
        })
        cls.other = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Other operator', 'login': 'nexar_test_other',
            'company_id': cls.company.id, 'company_ids': [Command.set(cls.company.ids)],
            'group_ids': [Command.set([group.id, cls.env.ref('base.group_user').id])],
        })
        cls.circuit = cls.env['nexar.test.circuit'].search([('company_id', '=', cls.company.id)], limit=1)
        if cls.circuit:
            cls.circuit.user_id = cls.owner
        else:
            cls.circuit = cls.env['nexar.test.circuit'].create({
                'name': 'Test', 'company_id': cls.company.id, 'user_id': cls.owner.id,
            })
        cls.accounts = cls.env['nexar.test.account'].create([
            {'circuit_id': cls.circuit.id, 'name': 'A', 'code': 'TEST-A'},
            {'circuit_id': cls.circuit.id, 'name': 'B', 'code': 'TEST-B'},
        ])
        cls.journal = cls.env['nexar.test.journal'].create({
            'circuit_id': cls.circuit.id, 'name': 'Test', 'code': 'TEST',
            'kind': 'general',
        })

    def make_move(self, amount=100):
        return self.env['nexar.test.move'].with_user(self.owner).create({
            'journal_id': self.journal.id,
            'line_ids': [
                Command.create({'account_id': self.accounts[0].id, 'label': 'Debit', 'debit': amount}),
                Command.create({'account_id': self.accounts[1].id, 'label': 'Credit', 'credit': amount}),
            ],
        })

    def test_post_edit_and_retry(self):
        move = self.make_move()
        move.action_post()
        name = move.name
        move.action_post()
        self.assertEqual(move.name, name)
        with self.assertRaises(UserError), self.cr.savepoint():
            move.line_ids[0].write({'debit': 50})
        move.action_draft()
        move.write({'ref': 'Edited'})
        move.action_post()
        self.assertEqual(move.name, name)

    def test_other_user_cannot_read_or_create(self):
        move = self.make_move()
        self.assertFalse(self.env['nexar.test.move'].with_user(self.other).search([('id', '=', move.id)]))
        with self.assertRaises(AccessError), self.cr.savepoint():
            move.with_user(self.other).read(['name'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['nexar.test.move'].with_user(self.other).create({'journal_id': self.journal.id})

    def test_direct_state_and_unbalanced_post_rejected(self):
        move = self.make_move()
        with self.assertRaises(AccessError), self.cr.savepoint():
            move.write({'state': 'posted'})
        move.line_ids[0].write({'debit': 50})
        with self.assertRaises(ValidationError), self.cr.savepoint():
            move.action_post()

    def test_no_fiscal_entries_created(self):
        before = self.env['account.move'].search_count([])
        self.make_move().action_post()
        self.assertEqual(before, self.env['account.move'].search_count([]))

    def test_direct_posted_creation_rejected(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['nexar.test.move'].with_user(self.owner).create({
                'journal_id': self.journal.id, 'state': 'posted',
            })

    def test_other_company_account_rejected(self):
        company = self.env['res.company'].create({'name': 'Additional test company'})
        self.owner.write({'company_ids': [Command.link(company.id)]})
        circuit = self.env['nexar.test.circuit'].create({
            'name': 'Other company circuit', 'company_id': company.id,
            'user_id': self.owner.id,
        })
        account = self.env['nexar.test.account'].create({
            'circuit_id': circuit.id, 'code': 'CROSS', 'name': 'Cross company',
        })
        move = self.make_move().with_context(allowed_company_ids=[self.company.id, company.id])
        with self.assertRaises((ValidationError, UserError)), self.cr.savepoint():
            move.line_ids[0].write({'account_id': account.id})

    def test_normal_internal_user_has_no_access(self):
        self.other.write({'group_ids': [Command.set([self.env.ref('base.group_user').id])]})
        move = self.make_move()
        for record in (self.circuit, self.journal, self.accounts, move, move.line_ids):
            with self.assertRaises(AccessError), self.cr.savepoint():
                record.with_user(self.other).read(['id'])

    def test_operator_cannot_configure_circuits(self):
        with self.assertRaises(AccessError), self.cr.savepoint():
            self.env['nexar.test.setup'].with_user(self.owner).create({
                'user_id': self.owner.id,
                'company_ids': [Command.set(self.company.ids)], 'acknowledge': True,
            })

    def test_fiscal_rules_deny_write_even_with_accountant_group(self):
        self.owner.write({'group_ids': [Command.link(self.env.ref('account.group_account_user').id)]})
        journal = self.env['account.journal'].search([('company_id', '=', self.company.id)], limit=1)
        if not journal:
            self.skipTest('No fiscal journal in the test database')
        journal.with_user(self.owner).read(['name'])
        with self.assertRaises(AccessError), self.cr.savepoint():
            journal.with_user(self.owner).write({'name': 'Forbidden'})
