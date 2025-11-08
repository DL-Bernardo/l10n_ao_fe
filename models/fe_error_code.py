# -*- coding: utf-8 -*-
from odoo import models, fields

class FEErrorCode(models.Model):
    """
    Mapeia os códigos de erro retornados pela API da AGT para mensagens
    descritivas e traduzíveis, facilitando o diagnóstico de problemas
    pelo utilizador final.
    """
    _name = 'l10n_ao.fe.error.code'
    _description = 'Códigos de Erro da Facturação Electrónica (AGT)'
    _order = 'code'

    code = fields.Char(string="Código", required=True, index=True)
    description = fields.Text(string="Descrição", required=True, translate=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'O código de erro deve ser único!'),
    ]
