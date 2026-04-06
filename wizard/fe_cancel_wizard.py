# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class L10nAoFeCancelWizard(models.TransientModel):
    _name = 'l10n_ao.fe.cancel.wizard'
    _description = 'Assistente para Anular Factura na AGT'

    move_id = fields.Many2one('account.move', string="Fatura", required=True)
    cancel_reason = fields.Selection([
        ('I', 'Anulada por incorrecta identificação do adquirente ( I )'),
        ('N', 'Anulada por não ter sido enviado o documento ao adquirente ( N )')
    ], string="Motivo da Anulação", required=True, default='I')

    def action_confirm_cancel(self):
        self.ensure_one()
        move = self.move_id
        
        # Chama a API de registo com a flag enviando a razao
        service = self.env['l10n_ao.fe.service'].with_company(move.company_id)
        
        try:
            # Chama registar_factura passando a razao
            response = service.registar_factura(move, cancel_reason=self.cancel_reason)
            
            # Atualiza o estado da factura pra anulado
            move.write({
                'fe_status': 'cancelled',
            })
            
            move.message_post(body=_("Factura Anulada na AGT com sucesso. Motivo: %s", self.cancel_reason))
            
            # Chama o cancelamento base do ERP se Odoo permitir (alguns estados não deixam)
            if move.state != 'cancel':
                move.with_context(force_cancel_agt=True).button_cancel()
                
        except Exception as e:
            raise UserError(_("Erro ao tentar anular a fatura na AGT: %s") % str(e))
