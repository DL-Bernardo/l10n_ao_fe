# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class AccountPaymentInherit(models.Model):
    _inherit = 'account.payment'

    fe_request_id = fields.Char(string='AGT Request ID', readonly=True, copy=False)
    fe_submission_uuid = fields.Char(string="AGT Submission UUID", copy=False, readonly=True)
    
    fe_status = fields.Selection([
        ('not_sent', 'Não Enviado'),
        ('processing', 'Em Processamento'),
        ('sent', 'Enviado'),
        ('validated', 'Validado'),
        ('error', 'Erro'),
        ('cancelled', 'Anulado')
    ], string="Estado FE", default='not_sent', copy=False, tracking=True)

    fe_payload_json = fields.Text(string="Último Payload JSON", copy=False, readonly=True)
    fe_document_hash = fields.Char(string="Hash AGT", copy=False, readonly=True)
    
    fe_jws_document_signature = fields.Text(string="JWS Document Signature", copy=False, readonly=True)
    fe_jws_software_signature = fields.Text(string="JWS Software Signature", copy=False, readonly=True)
    
    fe_sent_datetime = fields.Datetime(string="Data de Submissão AGT", copy=False, readonly=True)
    fe_error_list = fields.Text(string="Lista de Erros", copy=False, readonly=True)

    l10n_ao_fe_serie_id = fields.Many2one(
        'l10n_ao.fe.serie', 
        string="Série de FE", 
        readonly=True, 
        states={'draft': [('readonly', False)]},
        copy=False
    )

    def action_send_fe_agt(self):
        """Gera o payload, envia para AGT e processa a resposta."""
        service = self.env['l10n_ao.fe.service']
        
        for payment in self:
            if payment.state != 'posted':
                raise UserError(_("Apenas pagamentos no estado 'Lançado' podem ser enviados à AGT."))
            
            payment.write({'fe_status': 'processing'})
            
            try:
                response = service.registar_recibo(payment)
                
                # Processar resposta básica (melhorar conforme account_move_inherit)
                request_id = response.get("requestID")
                if request_id:
                    payment.fe_request_id = request_id
                    payment.fe_status = 'sent'
                
            except Exception as e:
                payment.fe_status = 'error'
                payment.fe_error_list = str(e)
                raise e

    def open_payload_wizard(self):
        """Abre o wizard para mostrar o payload JSON."""
        self.ensure_one()
        
        # Regenerar payload se não estiver validado, para refletir correções de código
        if self.fe_status != 'success':
            try:
                # Chama o serviço para gerar o JSON atualizado
                payload = self.env['l10n_ao.fe.service'].registar_recibo(self, preview=True)
            except Exception as e:
                payload = f"Erro ao gerar preview: {str(e)}"
        else:
            payload = self.fe_payload_json or "Payload não disponível."

        return {
            'name': _('Payload JSON'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.payload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_json_payload': payload}
        }

    def open_obter_estado_wizard(self):
        self.ensure_one()
        return {
            'name': _('Obter Estado AGT'),
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.get.state.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_request_id': self.fe_request_id,
                'default_tax_registration_number': self.company_id.vat
            }
        }
