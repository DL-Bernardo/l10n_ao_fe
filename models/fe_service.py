# -*- coding: utf-8 -*-
import json
import uuid
import datetime
import requests
from jose import jws
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class FeService(models.AbstractModel):
    _name = "l10n_ao.fe.service"
    _description = "Serviço de Facturação Electrónica AGT"

    # =====================================================
    # 🔧 CONFIGURAÇÃO E UTILITÁRIOS
    # =====================================================

    def _get_conf(self, param_name, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(f"l10n_ao_fe.{param_name}", default)

    def _get_private_key(self):
        """Lê a chave privada do caminho configurado."""
        private_key_path = self._get_conf("private_key_path")
        if not private_key_path:
            raise UserError(_("O caminho para a chave privada não está configurado (l10n_ao_fe.private_key_path)."))
        
        try:
            with open(private_key_path, 'r') as f:
                return f.read()
        except Exception as e:
            raise UserError(_("Erro ao ler chave privada em %s: %s", private_key_path, e))

    def _log_communication(self, endpoint, type_msg, payload, response=None, status=None, move_id=None, request_id=None):
        """Regista logs na tabela l10n_ao.fe.log"""
        try:
            self.env['l10n_ao.fe.log'].create({
                'name': endpoint,
                'type': type_msg,
                'url': self._get_base_url() + endpoint,
                'payload': payload,
                'response': response,
                'http_status': str(status) if status else False,
                'move_id': move_id,
                'request_id': request_id
            })
        except Exception as e:
            _logger.error("Falha ao gravar log FE: %s", e)

    def _get_base_url(self):
        return self._get_conf("base_url", "https://sifphml.minfin.gov.ao/sigt/fe/v1")

    # =====================================================
    # 🔐 ASSINATURAS JWS (CORE)
    # =====================================================

    def _sign_payload(self, payload_dict):
        """
        Assina um dicionário usando RS256 e a chave privada configurada.
        Retorna a string JWS (Compact Serialization).
        """
        private_key = self._get_private_key()
        try:
            # O payload deve ser um JSON string antes de assinar? 
            # A lib python-jose aceita dict e faz a serialização, mas para garantir a ordem e formato exato
            # que a AGT espera, às vezes é melhor controlar o json.dumps.
            # Contudo, o padrão JWS é assinar o payload (claims).
            return jws.sign(payload_dict, private_key, algorithm='RS256')
        except Exception as e:
            raise UserError(_("Erro ao gerar assinatura JWS: %s", e))

    def _get_software_signature(self):
        """
        Gera a assinatura do SOFTWARE (jwsSoftwareSignature).
        Assina apenas: productId, productVersion, softwareValidationNumber.
        """
        payload = {
            "productId": self._get_conf("product_id", "DIGITALUB-FE"),
            "productVersion": self._get_conf("product_version", "1.0.0"),
            "softwareValidationNumber": self._get_conf("software_validation_number", "0000/AGT/2025")
        }
        return self._sign_payload(payload), payload

    def _get_document_signature(self, move, doc_data):
        """
        Gera a assinatura do DOCUMENTO (jwsDocumentSignature).
        Assina os campos específicos do documento conforme spec.
        """
        # Campos obrigatórios para assinatura do documento (RegistarFactura)
        # Confirmar lista exata no spec. Geralmente inclui totais.
        
        fields_to_sign = {
            "documentNo": doc_data.get("documentNo"),
            "documentDate": doc_data.get("documentDate"),
            "documentType": doc_data.get("documentType"),
            "companyName": doc_data.get("companyName"),
            "customerTaxID": doc_data.get("customerTaxID"),
            "customerCountry": doc_data.get("customerCountry"),
            "documentTotals": doc_data.get("documentTotals"),
            # Adicionar outros campos se o spec exigir (ex: taxRegistrationNumber do emissor)
            "taxRegistrationNumber": move.company_id.vat, 
        }
        
        return self._sign_payload(fields_to_sign)

    def _get_issuer_signature(self, fields_dict):
        """
        Gera a assinatura do EMISSOR (jwsSignature) para os serviços que a exigem (ObterEstado, etc).
        Recebe um dict com os campos a assinar.
        """
        return self._sign_payload(fields_dict)

    # =====================================================
    # 🚀 SERVIÇOS REST (ENDPOINTS)
    # =====================================================

    def registar_factura(self, move):
        """
        Endpoint: /registarFactura
        Monta payload, assina e envia.
        """
        endpoint = "/registarFactura"
        url = self._get_base_url() + endpoint
        
        # 1. Preparar dados
        submission_uuid = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # Assinatura Software
        jws_software, software_info_detail = self._get_software_signature()
        
        # Linhas
        lines = []
        for i, line in enumerate(move.invoice_line_ids.filtered(lambda l: not l.display_type), 1):
             # Lógica de impostos simplificada (deve ser refinada com mapeamento real)
            tax = line.tax_ids[:1]
            tax_code = tax.l10n_ao_fe_exemption_code or 'NOR' if tax else 'NOR' # Exemplo
            tax_percentage = tax.amount if tax else 14.0
            
            lines.append({
                "lineNumber": str(i),
                "productCode": line.product_id.default_code or "S/COD",
                "productDescription": line.name[:200], # Limitar tamanho se necessário
                "quantity": str(line.quantity),
                "unitOfMeasure": line.product_uom_id.name or "Un",
                "unitPrice": str(line.price_unit),
                "debitAmount": str(line.price_subtotal), # Validar lógica debit/credit
                "creditAmount": "0.00",
                "taxPointDate": str(move.invoice_date),
                # Adicionar campos de imposto conforme spec
            })

        # Totais
        totals = {
            "taxPayable": str(move.amount_tax),
            "netTotal": str(move.amount_untaxed),
            "grossTotal": str(move.amount_total),
        }

        # Dados do Documento
        doc_data = {
            "documentNo": move.name,
            "documentStatus": "N", # Normal
            "documentDate": str(move.invoice_date),
            "documentType": move.l10n_ao_fe_document_class_id.code or "FT",
            "systemEntryDate": timestamp,
            "customerTaxID": move.partner_id.vat or "999999999",
            "customerCountry": move.partner_id.country_id.code or "AO",
            "companyName": move.company_id.name,
            "documentTotals": totals,
            "lines": lines
        }

        # Assinatura Documento
        jws_doc = self._get_document_signature(move, doc_data)
        doc_data["jwsDocumentSignature"] = jws_doc

        # Payload Principal
        payload = {
            "schemaVersion": "1.0",
            "submissionUUID": submission_uuid,
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": move.company_id.vat,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "numberOfEntries": "1",
            "documents": [doc_data]
        }

        payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
        
        # Guardar dados no move antes de enviar
        move.write({
            'fe_submission_uuid': submission_uuid,
            'fe_payload_json': payload_json,
            'fe_jws_software_signature': jws_software,
            'fe_jws_document_signature': jws_doc,
            'fe_document_hash': jws_doc,
            'fe_sent_datetime': fields.Datetime.now()
        })

        # Enviar
        self._log_communication(endpoint, 'request', payload_json, move_id=move.id)
        
        try:
            response = self._send_request(url, payload_json)
            
            # Processar resposta
            resp_json = response.json()
            resp_str = json.dumps(resp_json, indent=2, ensure_ascii=False)
            self._log_communication(endpoint, 'response', payload_json, resp_str, response.status_code, move_id=move.id, request_id=resp_json.get('requestID'))
            
            return resp_json
            
        except Exception as e:
            self._log_communication(endpoint, 'error', payload_json, str(e), move_id=move.id)
            raise e

    def obter_estado(self, request_id, tax_registration_number):
        """
        Endpoint: /obterEstado
        """
        endpoint = "/obterEstado"
        url = self._get_base_url() + endpoint
        
        # Assinatura do Emissor (Campos: taxRegistrationNumber, requestID)
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "requestID": request_id
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        jws_software, software_info_detail = self._get_software_signature()

        payload = {
            "schemaVersion": "1.0",
            "taxRegistrationNumber": tax_registration_number,
            "requestID": request_id,
            "submissionTimeStamp": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "jwsSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        self._log_communication(endpoint, 'request', payload_json, request_id=request_id)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def consultar_factura(self, document_no, tax_registration_number):
        """
        Endpoint: /consultarFactura
        """
        endpoint = "/consultarFactura"
        url = self._get_base_url() + endpoint
        
        # Assinatura do Emissor (Campos: taxRegistrationNumber, documentNo)
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "documentNo": document_no
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.0",
            "taxRegistrationNumber": tax_registration_number,
            "documentNo": document_no,
            "jwsSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        self._log_communication(endpoint, 'request', payload_json)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def listar_facturas(self, date_from, date_to, tax_registration_number):
        """
        Endpoint: /listarFacturas
        """
        endpoint = "/listarFacturas"
        url = self._get_base_url() + endpoint
        
        # Assinatura do Emissor (Campos: taxRegistrationNumber, queryStartDate, queryEndDate)
        # Nota: Datas devem estar no formato YYYY-MM-DD
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "queryStartDate": str(date_from),
            "queryEndDate": str(date_to)
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.0",
            "taxRegistrationNumber": tax_registration_number,
            "queryStartDate": str(date_from),
            "queryEndDate": str(date_to),
            "jwsSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        self._log_communication(endpoint, 'request', payload_json)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def _send_request(self, url, payload_json):
        """Função genérica de envio com Auth Basic"""
        username = self._get_conf("username")
        password = self._get_conf("password")
        
        if not username or not password:
             raise UserError(_("Credenciais AGT não configuradas."))

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        }
        
        try:
            resp = requests.post(
                url, 
                data=payload_json.encode('utf-8'), 
                headers=headers, 
                auth=(username, password),
                timeout=60
            )
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            if e.response:
                 raise UserError(_("Erro AGT (%s): %s", e.response.status_code, e.response.text))
            raise UserError(_("Erro de conexão: %s", e))

