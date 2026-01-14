# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FeSolicitarSerieWizard(models.TransientModel):
    _name = 'l10n_ao.fe.solicitar.serie.wizard'
    _description = 'Wizard para Solicitar Série de FE à AGT'

    serie_code = fields.Char(string="Código da Série", required=True)
    document_class_id = fields.Many2one(
        'l10n_ao.fe.document.class', 
        string="Tipo de Documento", 
        required=True
    )
    start_number = fields.Integer(string="Número Inicial", default=1, required=True)
    end_number = fields.Integer(string="Número Final", required=True)
    start_date = fields.Date(string="Data de Início", default=fields.Date.context_today, required=True)
    end_date = fields.Date(string="Data de Fim")
    establishment_number = fields.Char(string="Número do Estabelecimento", default="SEDE", required=True)

    def action_solicitar_serie(self):
        self.ensure_one()
        service = self.env['l10n_ao.fe.service']
        
        try:
            # Quantidade solicitada: end - start + 1
            qty = self.end_number - self.start_number + 1
            
            resp = service.solicitar_serie(
                "N", # seriesType Normal
                self.document_class_id.code,
                qty,
                "Utilizacao para emissao de facturas no sistema", # Justificação padrão
                self.env.company.vat,
                establishment_number=self.establishment_number
            )
            
            result_code = resp.get('resultCode')
            
            if result_code == 1:
                series_result = resp.get('seriesFEResult', {})
                series_code = series_result.get('seriesCode')
                
                if not series_code:
                    raise UserError("A AGT não retornou o código da série.")

                # Criar sequência no Odoo
                sequence = self.env['ir.sequence'].create({
                    'name': f'Série FE {series_code}',
                    'code': f'l10n_ao.fe.serie.{series_code}',
                    'prefix': f'{series_code}/',
                    'padding': 0,
                    'number_next': int(series_result.get('firstDocumentNo', 1)),
                    'company_id': self.env.company.id,
                })
                
                # Cap values to fit in PostgreSQL Integer (2147483647)
                MAX_INT = 2147483647
                last_no = int(series_result.get('lastDocumentNo', 0))
                auth_qty = int(series_result.get('authorizedQuantity', 0))
                
                if last_no > MAX_INT:
                    last_no = MAX_INT
                if auth_qty > MAX_INT:
                    auth_qty = MAX_INT

                # Criar registo da série
                self.env['l10n_ao.fe.serie'].create({
                    'name': series_code,
                    'document_class_id': self.document_class_id.id,
                    'sequence_id': sequence.id,
                    'start_date': self.start_date,
                    'end_date': self.end_date,
                    'first_number': int(series_result.get('firstDocumentNo', 0)),
                    'last_number': last_no,
                    'next_number': int(series_result.get('firstDocumentNo', 0)),
                    'authorized_quantity': auth_qty,
                    'agt_status': 'active',
                    'active': True
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Sucesso'),
                        'message': _('Série %s solicitada e criada com sucesso!', series_code),
                        'sticky': False,
                    }
                }
            else:
                error_list = resp.get('errorList', [])
                msg = "\n".join([f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list])
                raise UserError(f"Erro AGT: {msg}")

        except Exception as e:
            raise UserError(f"Falha ao solicitar série: {e}")
