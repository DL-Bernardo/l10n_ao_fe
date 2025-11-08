# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class FESerie(models.Model):
    """
    Armazena as séries de faturação eletrónica. Uma série é um conjunto de
    regras de numeração para um determinado tipo de documento fiscal,
    previamente autorizada pela AGT.
    """
    _name = 'l10n_ao.fe.serie'
    _description = 'Séries de Facturação Electrónica (AGT)'
    _order = 'name desc'

    name = fields.Char(string="Código da Série", required=True, index=True, help="Código único da série (ex: S2025)")
    document_class_id = fields.Many2one(
        'l10n_ao.fe.document.class',
        string="Tipo de Documento",
        required=True
    )
    start_date = fields.Date(string="Data de Início", required=True, default=fields.Date.today)
    end_date = fields.Date(string="Data de Fim", help="Data em que a série expira.")
    sequence_id = fields.Many2one('ir.sequence', string="Sequência Odoo", readonly=True, copy=False)
    company_id = fields.Many2one('res.company', string='Empresa', required=True, default=lambda self: self.env.company)
    active = fields.Boolean(string="Activa", default=True, help="Se desmarcado, a série não poderá ser usada.")
    agt_status = fields.Selection([
        ('draft', 'Rascunho'),
        ('pending', 'Pendente de Confirmação'),
        ('active', 'Activa'),
        ('rejected', 'Rejeitada'),
        ('expired', 'Expirada'),
    ], string="Estado AGT", readonly=True, default='draft', copy=False)

    _sql_constraints = [
        ('name_company_uniq', 'unique(name, company_id)', 'A série deve ser única por empresa!'),
    ]

    @api.model
    def action_update_agt_series_list(self):
        """
        Contacta o endpoint 'listarSeries' da AGT para obter a lista de séries
        autorizadas e cria ou atualiza os registos correspondentes no Odoo.
        """
        _logger.info("A iniciar a atualização da lista de séries da AGT.")
        service = self.env['l10n_ao.fe.service']
        code, resp = service.listar_series()

        if code != 200:
            self.env['l10n_ao.fe.service']._handle_error_response(code, resp)

        series_from_agt = resp.get('series', [])
        if not series_from_agt:
            raise UserError("A AGT não retornou nenhuma série na sua resposta.")

        doc_classes = self.env['l10n_ao.fe.document.class'].search([])
        doc_class_map = {dc.code: dc.id for dc in doc_classes}
        updated_count = 0
        created_count = 0

        for agt_serie in series_from_agt:
            serie_code = agt_serie.get('serieCode')
            if not serie_code:
                continue

            existing_serie = self.search([
                ('name', '=', serie_code),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            doc_class_id = doc_class_map.get(agt_serie.get('documentClass'))
            if not doc_class_id:
                _logger.warning(f"Tipo de documento '{agt_serie.get('documentClass')}' desconhecido. A saltar série '{serie_code}'.")
                continue

            vals = {
                'name': serie_code,
                'document_class_id': doc_class_id,
                'start_date': agt_serie.get('startDate'),
                'end_date': agt_serie.get('endDate'),
                'agt_status': 'active',  # As séries listadas estão, por definição, ativas na AGT
                'active': True,
            }

            if not existing_serie:
                self.create(vals)
                created_count += 1
            else:
                existing_serie.write(vals)
                updated_count += 1
        
        _logger.info(f"Atualização concluída: {created_count} séries criadas, {updated_count} atualizadas.")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Sucesso',
                'message': f'{created_count} séries criadas e {updated_count} atualizadas.',
                'sticky': False,
            }
        }
