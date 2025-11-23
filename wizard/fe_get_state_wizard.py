# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json

class FeGetStateWizard(models.TransientModel):
    _name = "l10n_ao.fe.get.state.wizard"
    _description = "Wizard para Obter Estado AGT"

    request_id = fields.Char(string="Request ID", required=True)
    tax_registration_number = fields.Char(string="NIF do Emissor", required=True, default=lambda self: self.env.company.vat)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_get_state(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        # Chama o serviço
        response = service.obter_estado(self.request_id, self.tax_registration_number)
        
        # Formata a resposta
        self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        
        # Processar a resposta e atualizar faturas
        doc_status_list = response.get('documentStatusList', [])
        if doc_status_list:
            for doc_info in doc_status_list:
                doc_no = doc_info.get('documentNo')
                status = doc_info.get('documentStatus')
                error_list = doc_info.get('errorList', [])
                
                # Procurar a fatura pelo número
                moves = self.env['account.move'].search([('name', '=', doc_no)])
                
                for move in moves:
                    new_status = move.fe_status
                    if status == 'V':
                        new_status = 'validated'
                        # Gerar QR Code se validado
                        if hasattr(move, 'generate_qr_code'):
                            move.generate_qr_code()
                    elif status in ('I', 'E'):
                        new_status = 'error'
                        move.fe_error_list = str(error_list)
                    
                    move.write({
                        'fe_status': new_status,
                        'fe_last_response': self.response_json
                    })
                    
                    # Logar no chatter
                    move.message_post(body=_("Estado atualizado via Obter Estado: %s", new_status))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.get.state.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
