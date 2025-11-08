{
    'name': 'Angola - Facturação Electrónica (AGT) Integration',
    'version': '1.0.2',
    'category': 'Accounting',
    'summary': 'Integração com a plataforma FE da AGT (registarFactura, obterEstado, consultarFactura, listarFacturas)',
    'description': """
Módulo que permite enviar facturas ao serviço FE da AGT, consultar estado e listar facturas.
Compatível com o ambiente de homologação 2025.
    """,
    'author': 'Digitalub / ContasMais',
    'license': 'AGPL-3',
    'depends': ['base', 'account'],

    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'data/fe_document_class_data.xml',
        'data/fe_error_code_data.xml',
        'views/account_move_views.xml',
        'views/fe_queue_views.xml',
        'views/fe_serie_views.xml',
        'wizard/fe_solicitar_serie_wizard_views.xml',
        'views/account_report_invoice_document.xml',
    ],
    'installable': True,
    'application': False,
    'images': ['static/description/banner.png'],
}