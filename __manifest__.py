{
    'name': 'Angola - Facturação Electrónica (AGT) Integration',
    'version': '1.2.0',
    'category': 'Accounting',
    'summary': 'Integração com a plataforma FE da AGT (Especificação 1.2)',
    'description': """
Módulo que permite enviar facturas ao serviço FE da AGT sob a especificação 1.2.
Compatível com o ambiente de homologação 2025.
    """,
    'author': 'Digitalub / ContasMais',
    'license': 'AGPL-3',
    'depends': ['base', 'account', 'account_debit_note'],

    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'data/ir_cron.xml',
        'data/fe_document_class_data.xml',
        'data/fe_error_code_data.xml',
        'views/account_tax_views.xml',
        'views/account_move_views.xml',
        'views/account_journal_views.xml',
        'views/ir_sequence_views.xml',
        'views/account_payment_views.xml',
        'views/account_payment_register_views.xml',
        'views/fe_queue_views.xml',
        'views/fe_serie_views.xml',
        'wizard/fe_solicitar_serie_wizard_views.xml',
        'wizard/account_move_reversal_views.xml',
        'wizard/account_debit_note_views.xml',
        'views/account_report_invoice_document.xml',
        'views/account_report_payment_receipt.xml',
        'views/fe_log_views.xml',
        'views/wizard_views.xml',
    ],
    'installable': True,
    'application': False,
    'images': ['static/description/banner.png'],
}