# -*- coding: utf-8 -*-
from odoo import models, fields

class FEDocumentClass(models.Model):
    """
    Representa os tipos de documentos fiscais permitidos pela AGT,
    conforme a especificação técnica. Exemplos: FT (Factura),
    NC (Nota de Crédito), etc.
    """
    _name = 'l10n_ao.fe.document.class'
    _description = 'Classe de Documento de Facturação Electrónica (AGT)'
    _order = 'name'

    name = fields.Char(string="Nome", required=True, translate=True)
    code = fields.Char(string="Código", required=True, help="O código oficial do tipo de documento (ex: FT).")

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'O código da classe de documento deve ser único!'),
    ]
