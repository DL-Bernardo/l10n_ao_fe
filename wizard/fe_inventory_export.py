# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import json
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class FEInventoryExportWizard(models.TransientModel):
    _name = 'l10n_ao_fe.inventory.export.wizard'
    _description = 'Exportação de SAF-T de Inventário AGT'

    year = fields.Selection([
        (str(y), str(y)) for y in range(datetime.now().year - 2, datetime.now().year + 1)
    ], string='Ano de Tributação', default=lambda self: str(datetime.now().year - 1), required=True)
    
    date_inventory = fields.Date(string='Data do Inventário', default=lambda self: datetime.now().replace(month=12, day=31).date(), required=True, help="Normalmente 31 de Dezembro do ano anterior.")
    
    costing_method = fields.Selection([
        ('CMP', 'CMP - Custo Médio Ponderado'),
        ('FIFO', 'FIFO - PEPS (Primeiro a Entrar, Primeiro a Sair)'),
        ('LIFO', 'LIFO - UEPS (Último a Entrar, Primeiro a Sair)'),
    ], string='Método de Custeio', default='CMP', required=True)

    no_operations = fields.Boolean(string='Sem Operações / Inventário Zero', default=False)
    
    ignore_history = fields.Boolean(
        string='Ignorar Histórico (Usar Stock Atual)', 
        default=False,
        help="Se marcado, o sistema usará o stock real atual em vez de tentar calcular "
             "as quantidades retroativas para a data selecionada. Útil para migrações de base de dados em 2026."
    )
    
    file_data = fields.Binary(string='Ficheiro SAF-T (XML/JSON)', readonly=True)
    file_name = fields.Char(string='Nome do Ficheiro', readonly=True)
    state = fields.Selection([('choose', 'Escolher'), ('get', 'Concluído')], default='choose')

    def action_generate_saft_inventory(self):
        self.ensure_one()
        
        company = self.env.company
        if not company.vat:
            raise UserError(_("O NIF da empresa não está configurado."))

        # Obter dados do serviço para cabeçalho
        fe_service = self.env['l10n_ao.fe.service']
        product_id = fe_service._get_conf("product_id", "DIGITALUB-FE")
        product_version = fe_service._get_conf("product_version", "1.1.0")
        software_validation_number = fe_service._get_conf("software_validation_number", "FE/00/AGT/2025")

        # 1. Cabeçalho (StockHeader)
        # Nota: A assinatura deve ser do cabeçalho ou software info
        jws_sig, _ = fe_service._get_software_signature()
        
        header = {
            "Assinatura": jws_sig,
            "TaxRegistrationNumber": company.vat,
            "DateCreated": datetime.now().strftime("%Y-%m-%d"),
            "SoftwareValidationNumber": software_validation_number,
            "ProductID": product_id,
            "ProductVersion": product_version,
            "AAAA": self.year,
            "Sem_Operacoes": "Sim" if self.no_operations else "Não"
        }

        stock_items = []
        if not self.no_operations:
            # Procure por produtos que podem ter stock (Detailed Type = product em v17)
            # Usamos detailed_type se existir, caso contrário type
            domain = ['|', ('type', '=', 'product'), ('detailed_type', '=', 'product')]
            products = self.env['product.product'].search(domain)
            
            _logger.info("SAF-T Inventário: %s produtos encontrados para análise.", len(products))
            
            for product in products:
                # Garantir o contexto da empresa para o cálculo do stock
                p_context = {'company_id': company.id}
                if not self.ignore_history:
                    p_context['to_date'] = self.date_inventory
                
                # Calcular quantidade disponível
                product_with_ctx = product.with_context(**p_context)
                qty = product_with_ctx.qty_available
                
                if qty <= 0:
                    continue
                    
                # Valor = Quantidade x Custo Unitário (Standard Price)
                value = product.standard_price * qty
                
                stock_items.append({
                    "Metodo_Custeio": self.costing_method,
                    "Tipo_Produto": product.fe_product_type or 'M',
                    "ProductCode": product.default_code or str(product.id),
                    "ProductDescription": product.name,
                    "Quantity": qty,
                    "UnitOfMeasure": product.uom_id.name or 'un',
                    "Value": round(value, 2)
                })
            
            _logger.info("SAF-T Inventário: %s linhas geradas para o XML.", len(stock_items))

        # Construir Ficheiro (XML conforme Circular 05/2026)
        xml_content = self._build_xml(header, stock_items)
        
        self.write({
            'file_data': base64.b64encode(xml_content.encode('utf-8')),
            'file_name': f'SAFT_Inventario_{self.year}_{company.vat}.xml',
            'state': 'get'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'l10n_ao_fe.inventory.export.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }

    def _build_xml(self, header, items):
        """Constrói o XML conforme a estrutura da AGT."""
        xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
        xml += '<AuditFile>\n'
        
        # Header (Conforme Tabela de Cabeçalho 1.1 a 1.8)
        xml += '  <StockHeader>\n'
        xml += f'    <Assinatura>{header["Assinatura"]}</Assinatura>\n'
        xml += f'    <TaxRegistrationNumber>{header["TaxRegistrationNumber"]}</TaxRegistrationNumber>\n'
        xml += f'    <DateCreated>{header["DateCreated"]}</DateCreated>\n'
        xml += f'    <SoftwareValidationNumber>{header["SoftwareValidationNumber"]}</SoftwareValidationNumber>\n'
        xml += f'    <ProductID>{header["ProductID"]}</ProductID>\n'
        xml += f'    <ProductVersion>{header["ProductVersion"]}</ProductVersion>\n'
        xml += f'    <AAAA>{header["AAAA"]}</AAAA>\n'
        xml += f'    <SemOperacoes>{header["Sem_Operacoes"]}</SemOperacoes>\n'
        xml += '  </StockHeader>\n'
        
        # Stock Table (Índices 0 a 6)
        xml += '  <Stock>\n'
        xml += f'    <TaxRegistrationNumber>{header["TaxRegistrationNumber"]}</TaxRegistrationNumber>\n'
        xml += f'    <Year>{header["AAAA"]}</Year>\n'
        
        for item in items:
            xml += '    <ProductStock>\n'
            xml += f'      <MetodoCusteio>{item["Metodo_Custeio"]}</MetodoCusteio>\n'
            xml += f'      <TipoProduto>{item["Tipo_Produto"]}</TipoProduto>\n'
            xml += f'      <ProductCode>{item["ProductCode"]}</ProductCode>\n'
            xml += f'      <ProductDescription>{item["ProductDescription"]}</ProductDescription>\n'
            xml += f'      <Quantity>{item["Quantity"]}</Quantity>\n'
            xml += f'      <UnitOfMeasure>{item["UnitOfMeasure"]}</UnitOfMeasure>\n'
            xml += f'      <Value>{item["Value"]}</Value>\n'
            xml += '    </ProductStock>\n'
        
        xml += '  </Stock>\n'
        xml += '</AuditFile>'
        return xml
