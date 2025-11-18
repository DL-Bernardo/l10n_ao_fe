# -*- coding: utf-8 -*-
import json
import uuid
import datetime
import requests
from jose import jws

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class FeService(models.AbstractModel):
    _name = "l10n_ao.fe.service"
    _description = "Serviço de Facturação Electrónica AGT"

    def _get_conf(self, param_name, default=None):
        return self.env["ir.config_parameter"].sudo().get_param(f"l10n_ao_fe.{param_name}", default)

    def _generate_invoice_payload(self, move):
        """Gera o payload JSON conforme o padrão da AGT."""
        # self.ensure_one() # Removed as this is an AbstractModel and ensure_one is not applicable here.

        # 🧾 1. Dados base do envio
        submission_uuid = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat()

        # ⚙️ 2. Assinatura do software
        private_key_path = self._get_conf("private_key_path")
        if not private_key_path:
            raise UserError(_("O caminho para a chave privada para a assinatura JWS não está configurado. Por favor, defina 'l10n_ao_fe.private_key_path' nos parâmetros do sistema."))

        try:
            with open(private_key_path, 'r') as f:
                private_key = f.read()
        except FileNotFoundError:
            raise UserError(_("O ficheiro da chave privada não foi encontrado no caminho especificado: %s", private_key_path))
        except Exception as e:
            raise UserError(_("Erro ao ler o ficheiro da chave privada: %s", e))

        software_payload = {
            "productId": self._get_conf("product_id", "DIGITALUB-FE"),
            "productVersion": self._get_conf("product_version", "1.0.0"),
            "softwareValidationNumber": self._get_conf("software_validation_number", "HML-TESTE-001")
        }
        
        try:
            software_signature = jws.sign(software_payload, private_key, algorithm="RS256")
        except Exception as e:
            _logger.error("Falha ao assinar o payload do software: %s", e)
            raise UserError(_("Falha ao assinar o payload do software. Verifique a chave privada. Erro: %s", e))

        # 💼 3. Linhas da fatura
        lines = []
        for i, line in enumerate(move.invoice_line_ids.filtered(lambda l: not l.display_type), 1):
            tax_percentage = 0.0
            tax_exemption_reason = "M00" # Isento por defeito
            tax_exemption_code = "NS" # Não sujeito por defeito

            if line.tax_ids:
                # Assumindo o primeiro imposto para simplificação
                tax = line.tax_ids[0]
                tax_percentage = tax.amount
                if tax.l10n_ao_fe_exemption_code:
                    tax_exemption_reason = tax.l10n_ao_fe_exemption_reason or ''
                    tax_exemption_code = tax.l10n_ao_fe_exemption_code
                else:
                    tax_exemption_reason = ""
                    tax_exemption_code = ""


            lines.append({
                "lineNumber": str(i),
                "productCode": line.product_id.default_code or f"PROD-{line.product_id.id}",
                "productDescription": line.name,
                "quantity": line.quantity,
                "unitOfMeasure": line.product_uom_id.name or "Un",
                "unitPrice": line.price_unit,
                "taxPointDate": move.invoice_date.strftime("%Y-%m-%d"),
                "taxExemptionReason": tax_exemption_reason,
                "taxExemptionCode": tax_exemption_code,
                "taxPercentage": tax_percentage,
                "debitAmount": line.price_subtotal if move.move_type in ('out_invoice', 'in_refund') else 0.0,
                "creditAmount": line.price_subtotal if move.move_type in ('out_refund', 'in_invoice') else 0.0,
            })

        # 🧩 4. Assinatura do documento (fatura)
        document_payload = {
            "documentNo": move.name,
            "companyName": move.company_id.name,
            "taxRegistrationNumber": move.company_id.vat,
            "timestamp": timestamp,
        }
        try:
            document_signature = jws.sign(document_payload, private_key, algorithm="RS256")
        except Exception as e:
            _logger.error("Falha ao assinar o payload do documento: %s", e)
            raise UserError(_("Falha ao assinar o payload do documento. Verifique a chave privada. Erro: %s", e))

        # 🧠 5. Montagem final do JSON
        document_type = move.l10n_ao_fe_document_class_id.code if move.l10n_ao_fe_document_class_id else 'FT'
        
        payload = {
            "schemaVersion": "1.0",
            "submissionUUID": submission_uuid,
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": move.company_id.vat,
            "softwareInfo": {
                "softwareInfoDetail": software_payload,
                "jwsSoftwareSignature": software_signature,
            },
            "numberOfEntries": 1,
            "documents": [
                {
                    "documentNo": move.name,
                    "documentStatus": "N",
                    "documentDate": str(move.invoice_date),
                    "documentType": document_type,
                    "systemEntryDate": timestamp,
                    "customerTaxID": move.partner_id.vat or "999999999",
                    "customerCountry": move.partner_id.country_id.code or "AO",
                    "companyName": move.company_id.name,
                    "documentTotals": {
                        "netTotal": move.amount_untaxed,
                        "grossTotal": move.amount_total,
                        "taxPayable": move.amount_tax,
                    },
                    "lines": lines,
                    "jwsDocumentSignature": document_signature,
                }
            ],
        }

        return json.dumps(payload, indent=2, ensure_ascii=False)

    def _get_agt_status(self, submission_uuid):
        """Consulta o estado de uma submissão na AGT usando o endpoint ObterEstado."""
        url = self._get_conf("base_url", "https://sifphml.minfin.gov.ao/sigt/fe/v1") + "/obterEstado"
        username = self._get_conf("username")
        password = self._get_conf("password")

        if not username or not password:
            raise UserError(_("As credenciais de acesso à AGT (username/password) não estão configuradas."))

        # Assuming submissionUUID is passed as a query parameter
        params = {'submissionUUID': submission_uuid}

        _logger.info("Consultando estado na AGT para submissionUUID %s em %s", submission_uuid, url)

        try:
            resp = requests.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                },
                auth=(username, password),
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error("Erro de comunicação com a AGT ao consultar estado: %s", e)
            raise UserError(_("Erro de comunicação com a AGT ao consultar estado: %s", e))

        _logger.info("Resposta da AGT ao consultar estado: %s", resp.status_code)
        _logger.debug("Corpo da resposta ao consultar estado: %s", resp.text)

        if resp.status_code == 200:
            return resp.json()
        else:
            try:
                error_data = resp.json()
                error_list = error_data.get("errorList", [])
                error_msgs = [f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list]
                raise UserError(_("A AGT retornou um erro ao consultar estado:\n%s", "\n".join(error_msgs)))
            except json.JSONDecodeError:
                raise UserError(_("A AGT retornou uma resposta inesperada ao consultar estado (HTTP %s): %s", resp.status_code, resp.text))

    def _send_to_agt(self, payload_json):
        """Envia o payload JSON para o endpoint da AGT."""
        url = self._get_conf("base_url", "https://sifphml.minfin.gov.ao/sigt/fe/v1") + "/registarFactura"
        username = self._get_conf("username")
        password = self._get_conf("password")

        if not username or not password:
            raise UserError(_("As credenciais de acesso à AGT (username/password) não estão configuradas."))

        _logger.info("Enviando payload para AGT em %s", url)
        _logger.debug("Payload: %s", payload_json)

        try:
            resp = requests.post(
                url,
                data=payload_json.encode('utf-8'),
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Accept": "application/json",
                },
                auth=(username, password),
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error("Erro de comunicação com a AGT: %s", e)
            raise UserError(_("Erro de comunicação com a AGT: %s", e))

        _logger.info("Resposta da AGT: %s", resp.status_code)
        _logger.debug("Corpo da resposta: %s", resp.text)
        
        if resp.status_code in (200, 201, 202):
            return resp.json()
        else:
            try:
                error_data = resp.json()
                error_list = error_data.get("errorList", [])
                error_msgs = [f"({e.get('idError')}) {e.get('descriptionError')}" for e in error_list]
                raise UserError(_("A AGT retornou um erro:\n%s", "\n".join(error_msgs)))
            except json.JSONDecodeError:
                raise UserError(_("A AGT retornou uma resposta inesperada (HTTP %s): %s", resp.status_code, resp.text))
