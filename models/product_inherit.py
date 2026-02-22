# -*- coding: utf-8 -*-
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    fe_product_type = fields.Selection([
        ('M', 'M - Mercadorias'),
        ('P', 'P - Matérias-primas, subsidiárias e de consumo'),
        ('A', 'A - Produtos acabados e intermédios'),
        ('S', 'S - Subprodutos, desperdícios e refugos'),
        ('T', 'T - Produtos e trabalhos em curso'),
        ('B', 'B - Activos biológicos'),
    ], string='Tipo de Produto (AGT)', default='M', help="Tipo de produto para o SAF-T de Inventário")
