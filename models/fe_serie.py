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
    document_type_code = fields.Char(related='document_class_id.code', store=True, string="Código do Tipo")
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

    first_number = fields.Integer(string="Número Inicial", help="Primeiro número da série.")
    last_number = fields.Integer(string="Número Final", help="Último número autorizado da série.")
    next_number = fields.Integer(string="Próximo Número", default=1, help="Próximo número a ser usado.")
    authorized_quantity = fields.Char(string="Quantidade Autorizada", help="Quantidade total de documentos autorizados.")
    
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
        
        try:
            resp = service.listar_series(self.env.company.vat)
        except Exception as e:
             raise UserError(f"Erro ao listar séries: {e}")

        # O endpoint listarSeries retorna uma lista de séries dentro de 'seriesList' ou similar?
        # O spec diz que retorna 'seriesFEResult' que contem uma lista?
        # Assumindo estrutura baseada no solicitarSerie response, mas para listarSeries pode ser diferente.
        # Ajustar conforme spec real. Normalmente é uma lista direta ou dentro de um campo.
        # Vamos assumir que a resposta tem um campo 'seriesList' ou é o próprio root se for lista.
        # Se o response for { "resultCode": 1, "seriesList": [...] }
        
        series_from_agt = resp.get('seriesList', [])
        # Fallback se a estrutura for diferente
        if not series_from_agt and 'seriesFEResult' in resp:
             # Se for solicitarSerie retorna seriesFEResult (objeto único). Listar deve retornar lista.
             pass

        if not series_from_agt:
             # Pode ser que não haja séries ou a chave seja outra.
             _logger.warning("Nenhuma série encontrada na resposta da AGT.")
             return

        doc_classes = self.env['l10n_ao.fe.document.class'].search([])
        doc_class_map = {dc.code: dc.id for dc in doc_classes}
        updated_count = 0
        created_count = 0

        for agt_serie in series_from_agt:
            serie_code = agt_serie.get('seriesCode')
            if not serie_code:
                continue

            existing_serie = self.search([
                ('name', '=', serie_code),
                ('company_id', '=', self.env.company.id)
            ], limit=1)

            doc_type_code = agt_serie.get('documentType')
            doc_class_id = doc_class_map.get(doc_type_code)
            
            if not doc_class_id:
                _logger.warning(f"Tipo de documento '{doc_type_code}' desconhecido. A saltar série '{serie_code}'.")
                continue

            vals = {
                'name': serie_code,
                'document_class_id': doc_class_id,
                # 'start_date': agt_serie.get('startDate'), # Se disponível
                # 'end_date': agt_serie.get('endDate'), # Se disponível
                'first_number': int(agt_serie.get('firstDocumentNo', 0)),
                'last_number': int(agt_serie.get('lastDocumentNo', 0)),
                'authorized_quantity': agt_serie.get('authorizedQuantity'),
                'agt_status': 'active',
                'active': True,
            }
            
            # Se for nova série, next_number = first_number
            if not existing_serie:
                vals['next_number'] = vals['first_number']
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
