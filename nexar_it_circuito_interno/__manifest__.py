{
    'name': 'Nexar Circuito Interno',
    'version': '19.0.1.0.3',
    'summary': 'Circuito contable privado con cajas ARS y USD',
    'author': 'Nexar IT',
    'license': 'LGPL-3',
    'depends': ['account', 'account_reports', 'l10n_ar', 'vippinn_ea_analytic_control'],
    'data': ['security/groups.xml', 'security/ir.model.access.csv',
             'security/rules.xml', 'views/circuit_views.xml', 'views/user_views.xml'],
    'application': True,
    'installable': True,
}
