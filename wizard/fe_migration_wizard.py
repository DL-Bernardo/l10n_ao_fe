# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class FEMigrationWizard(models.TransientModel):
    _name = 'l10n_ao_fe.migration.wizard'
    _description = 'Assistente de Migração de Saldos para AGT'

    partner_id = fields.Many2one('res.partner', string="Parceiro", required=True)
    amount = fields.Float(string="Valor em Dívida", required=True)
    original_invoice_ref = fields.Char(string="Referência Fatura Antiga", required=True, 
                                      help="Ex: FT FA2024/001. Será enviada no campo 'ref' da fatura.")
    
    l10n_ao_fe_serie_id = fields.Many2one('l10n_ao.fe.serie', string="Série FE (2026)", required=True,
                                         domain=[('document_type_code', '=', 'FT'), ('active', '=', True)],
                                         help="Selecione uma série de 2026 autorizada para Faturas (FT).")
    
    migration_account_id = fields.Many2one('account.account', string="Conta de Contrapartida", required=True,
                                          help="Conta de 'Ajuste de Saldo' ou 'Câmara de Compensação' para não duplicar proveitos.")

    def action_register_migration(self):
        self.ensure_one()
        
        # 1. Procurar Diário de Vendas
        journal = self.env['account.journal'].search([('type', '=', 'sale')], limit=1)
        if not journal:
            raise UserError(_("Não foi encontrado um Diário de Vendas."))

        # 2. Procurar Imposto Isento (Padrão M10)
        tax = self.env['account.tax'].search([
            ('amount', '=', 0), 
            ('type_tax_use', '=', 'sale'),
            ('l10n_ao_fe_exemption_code', '=', 'M10')
        ], limit=1)
        if not tax:
            # Fallback para qualquer imposto 0% de vendas
            tax = self.env['account.tax'].search([('amount', '=', 0), ('type_tax_use', '=', 'sale')], limit=1)
        
        # 3. Criar Factura Espelho (FT)
        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': fields.Date.today(),
            'l10n_ao_fe_serie_id': self.l10n_ao_fe_serie_id.id,
            'ref': self.original_invoice_ref,
            'journal_id': journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': _('Regularização de Saldo Migrado - Ref Original: %s') % self.original_invoice_ref,
                'quantity': 1,
                'price_unit': self.amount,
                'account_id': self.migration_account_id.id,
                'tax_ids': [(6, 0, tax.ids)] if tax else [],
            })]
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        # 4. Enviar para AGT
        try:
            move.action_send_fe_agt()
        except Exception as e:
            _logger.error("Erro ao enviar fatura de migração para AGT: %s", e)
            # Não paramos a execução, o utilizador pode tentar reenviar depois
            
        # 5. Reconciliação Automática (Para anular o efeito no extrato do cliente)
        # Procuramos o lançamento de abertura (MISC) que gerou o saldo devedor
        # Procuramos linhas de 'receivable' abertas para este parceiro
        lines_to_reconcile = self.env['account.move.line'].search([
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted')
        ])
        
        # Filtrar a linha da nova FT e a linha do MISC de migração (se possível)
        new_move_line = move.line_ids.filtered(lambda l: l.account_id.account_type == 'asset_receivable')
        
        # Tentamos reconciliar a nova FT com o saldo de migração existente
        # Para que o saldo do parceiro continue a ser o mesmo (a FT aumenta o débito, 
        # mas como é uma "regularização", devemos abater no saldo de migração que já lá estava)
        # NOTA: Se o cliente quiser pagar a FT directamente, talvez não queira reconciliar agora.
        # Mas para a AGT o objectivo é substituir o saldo fantasma por uma FT real.
        
        return {
            'name': _('Factura de Migração Gerada'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
            'target': 'current',
        }
