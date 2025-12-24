# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json
import logging

_logger = logging.getLogger(__name__)

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
        _logger.info(f"FE AGT: Resposta recebida do Obter Estado: {self.response_json}")
        
        # Processar a resposta e atualizar faturas
        
        # Erros globais ou de requisição (que podem causar E08/E40)
        request_errors = response.get('requestErrorList', [])
        if isinstance(request_errors, list) and any(isinstance(e, dict) for e in request_errors):
            error_msg = "\n".join([f"({e.get('idError')}) {e.get('descriptionError')}" for e in request_errors if isinstance(e, dict)])
            _logger.error(f"FE AGT: Erros na requisição: {error_msg}")
            # Se houver erro global e apenas um movimento no wizard, podemos logar o erro nele
            # mas geralmente o wizard é genérico.

        doc_status_list = response.get('documentStatusList')
        if isinstance(doc_status_list, list):
            for doc_info in doc_status_list:
                if not isinstance(doc_info, dict):
                    continue

                doc_no = doc_info.get('documentNo')
                if not doc_no:
                    continue

                status = doc_info.get('documentStatus')
                error_list = doc_info.get('errorList', [])
                if not isinstance(error_list, list):
                    error_list = []
                
                # Filtrar apenas erros que sejam dicionários
                error_list = [e for e in error_list if isinstance(e, dict)]
                
                _logger.info(f"FE AGT: Processando estado para {doc_no} - Status: {status}")
                
                # Procurar a fatura pelo número
                moves = self.env['account.move'].search([('name', '=', doc_no)])
                
                if moves:
                    _logger.info(f"FE AGT: Encontradas {len(moves)} faturas (moves) para {doc_no}")
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
                        
                        _logger.info(f"FE AGT: Atualizando move {move.id} para {new_status}")
                        move.write({
                            'fe_status': new_status,
                            'fe_last_response': self.response_json
                        })
                        
                        # Logar no chatter
                        move.message_post(body=_("Estado atualizado via Obter Estado: %s", new_status))
                        
                        # Verificar se existe um pagamento associado a este movimento e atualizar também
                        payment = self.env['account.payment'].search([('move_id', '=', move.id)], limit=1)
                        if payment:
                            _logger.info(f"FE AGT: Atualizando pagamento relacionado {payment.id} para {new_status}")
                            vals_pay = {'fe_status': new_status}
                            if hasattr(payment, 'fe_last_response'):
                                vals_pay['fe_last_response'] = self.response_json
                            payment.write(vals_pay)
                            
                            if hasattr(payment, 'message_post'):
                                payment.message_post(body=_("Estado atualizado via Obter Estado (via movimento): %s", new_status))
                else:
                    _logger.info(f"FE AGT: Nenhuma fatura encontrada para {doc_no}. Procurando pagamentos...")
                    # Se não encontrar faturas, procurar pagamentos (Recibos)
                    payments = self.env['account.payment'].search([('name', '=', doc_no)])
                    _logger.info(f"FE AGT: Encontrados {len(payments)} pagamentos para {doc_no}")

                    for payment in payments:
                        new_status = payment.fe_status
                        if status == 'V':
                            new_status = 'validated'
                        elif status in ('I', 'E'):
                            new_status = 'error'
                            payment.fe_error_list = str(error_list)
                        
                        _logger.info(f"FE AGT: Atualizando payment {payment.id} para {new_status}")
                        
                        # Nota: account.payment pode não ter fe_last_response
                        vals = {'fe_status': new_status}
                        if hasattr(payment, 'fe_last_response'):
                             vals['fe_last_response'] = self.response_json
                             
                        payment.write(vals)
                        
                        if hasattr(payment, 'message_post'):
                             payment.message_post(body=_("Estado atualizado via Obter Estado: %s", new_status))

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao.fe.get.state.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
