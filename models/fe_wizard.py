# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import json
import logging

_logger = logging.getLogger(__name__)

class FePayloadWizard(models.TransientModel):
    _name = 'l10n_ao.fe.payload.wizard'
    _description = 'Wizard para mostrar Payload JSON'

    json_payload = fields.Text(string="Payload JSON", readonly=True)

class FeGetStateWizard(models.TransientModel):
    _name = 'l10n_ao.fe.get.state.wizard'
    _description = 'Wizard para Obter Estado AGT'

    request_id = fields.Char(string="Request ID", readonly=True)
    tax_registration_number = fields.Char(string="NIF Emissor", readonly=True)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_get_state(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        try:
            # Chamar serviço obter_estado
            response = service.obter_estado(self.request_id, self.tax_registration_number)
            self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
            
            # Atualizar o estado no documento original se possível
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            
            if active_model and active_id:
                record = self.env[active_model].browse(active_id)
                
                # A resposta tem documentStatusList -> [ { documentStatus: 'V'/'I', ... } ]
                doc_status_list = response.get('documentStatusList', [])
                if doc_status_list:
                    doc_info = doc_status_list[0]
                    status_code = doc_info.get('documentStatus')
                    
                    final_status = record.fe_status
                    if status_code == 'V':
                        final_status = 'validated'
                    elif status_code == 'I':
                        final_status = 'error'
                        error_list = doc_info.get('errorList', [])
                        error_msgs = "\n".join([f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list])
                        if hasattr(record, 'fe_error_list'):
                            record.fe_error_list = error_msgs
                    
                    if hasattr(record, 'fe_status'):
                        record.fe_status = final_status
                        
                    if hasattr(record, 'fe_last_response'):
                        record.fe_last_response = self.response_json
                        
                    # Se validado, tentar obter o hash via consultar_factura?
                    # O obterEstado não retorna o hash. O hash é gerado localmente (jwsDocumentSignature)
                    # e deve bater com o da AGT.
                    # O campo fe_document_hash no Odoo guarda o hash local.

        except Exception as e:
            self.response_json = f"Erro: {str(e)}"
            _logger.error("Erro no wizard obter estado: %s", e)

class FeConsultInvoiceWizard(models.TransientModel):
    _name = 'l10n_ao.fe.consult.invoice.wizard'
    _description = 'Wizard para Consultar Fatura AGT'

    document_no = fields.Char(string="Nº Documento", required=True)
    tax_registration_number = fields.Char(string="NIF Emissor", required=True)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_consult(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        try:
            response = service.consultar_factura(self.document_no, self.tax_registration_number)
            self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        except Exception as e:
            self.response_json = f"Erro: {str(e)}"

class FeListInvoicesWizard(models.TransientModel):
    _name = 'l10n_ao.fe.list.invoices.wizard'
    _description = 'Wizard para Listar Faturas AGT'

    date_from = fields.Date(string="Data Início", required=True)
    date_to = fields.Date(string="Data Fim", required=True)
    tax_registration_number = fields.Char(string="NIF Emissor", required=True)
    response_json = fields.Text(string="Resposta JSON", readonly=True)

    def action_list(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        try:
            response = service.listar_facturas(self.date_from, self.date_to, self.tax_registration_number)
            self.response_json = json.dumps(response, indent=2, ensure_ascii=False)
        except Exception as e:
            self.response_json = f"Erro: {str(e)}"
