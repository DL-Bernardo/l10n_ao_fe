# -*- coding: utf-8 -*-
import json
import uuid
import datetime
import requests
from jose import jws
import logging
import math
import decimal

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class FeService(models.AbstractModel):
    _name = "l10n_ao.fe.service"
    _description = "Serviço de Facturação Electrónica AGT"

    def _get_conf(self, param_name, default=None):
        val = self.env["ir.config_parameter"].sudo().get_param(f"l10n_ao_fe.{param_name}", default)
        return val.strip() if val and isinstance(val, str) else val

    def _get_private_key(self):
        private_key_path = self._get_conf("private_key_path")
        if not private_key_path:
            raise UserError(_("O caminho para a chave privada do SOFTWARE não está configurado."))
        try:
            with open(private_key_path, 'r') as f:
                return f.read()
        except Exception as e:
            raise UserError(_("Erro ao ler chave privada do SOFTWARE: %s", e))

    def _get_issuer_private_key(self):
        private_key_path = self._get_conf("issuer_private_key_path")
        if not private_key_path:
            raise UserError(_("O caminho para a chave privada do EMISSOR não está configurado."))
        try:
            with open(private_key_path, 'r') as f:
                return f.read()
        except Exception as e:
            raise UserError(_("Erro ao ler chave privada do EMISSOR: %s", e))

    def _log_communication(self, endpoint, type_msg, payload, response=None, status=None, move_id=None, request_id=None):
        if type_msg == 'request':
            _logger.info("AGT REQUEST [%s]: %s", endpoint, payload)
        elif type_msg == 'response':
            _logger.info("AGT RESPONSE [%s] (Status: %s): %s", endpoint, status, response)
        elif type_msg == 'error':
            _logger.error("AGT ERROR [%s]: %s - Payload: %s", endpoint, response, payload)

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

    def _sign_payload(self, payload_dict, key_type='software'):
        if key_type == 'issuer':
            private_key = self._get_issuer_private_key()
        else:
            private_key = self._get_private_key()
        try:
            # Header conforme exemplo da especificação AGT - Ordem e Conteúdo Cruciais
            header = {"typ": "JOSE", "alg": "RS256"}
            # Garantir JSON canónico (sem espaços) para a assinatura
            payload_json = json.dumps(payload_dict, separators=(',', ':'), ensure_ascii=False)
            _logger.debug("JWS payload [%s]: %s", key_type, payload_json)
            return jws.sign(payload_json.encode('utf-8'), private_key, algorithm='RS256', headers=header)
        except Exception as e:
            raise UserError(_("Erro ao gerar assinatura JWS (%s): %s", key_type, e))

    def _round_tax(self, amount):
        # Arredondamento por excesso (Ceiling) para o cêntimo seguinte
        return float(decimal.Decimal(str(amount)).quantize(decimal.Decimal('0.01'), rounding=decimal.ROUND_CEILING))

    def _get_software_signature(self):
        payload = {
            "productId": self._get_conf("product_id", "DIGITALUB-FE"),
            "productVersion": self._get_conf("product_version", "1.0.0"),
            "softwareValidationNumber": self._get_conf("software_validation_number", "FE/85/AGT/2025")
        }
        return self._sign_payload(payload, key_type='software'), payload

    def _get_document_signature(self, move, doc_data):
        # Ordem rigorosa conforme Payload assinatura Registar Factura da especificação
        fields_to_sign = {
            "documentNo": doc_data.get("documentNo"),
            "taxRegistrationNumber": move.company_id.vat,
            "documentType": doc_data.get("documentType"),
            "documentDate": doc_data.get("documentDate"),
            "customerTaxID": doc_data.get("customerTaxID"),
            "customerCountry": doc_data.get("customerCountry"),
            "companyName": doc_data.get("companyName"),
            "documentTotals": doc_data.get("documentTotals"),
        }
        return self._sign_payload(fields_to_sign, key_type='issuer')

    def _get_issuer_signature(self, fields_dict):
        return self._sign_payload(fields_dict, key_type='issuer')

    def registar_factura(self, move, preview=False):
        endpoint = "/registarFactura"
        url = self._get_base_url() + endpoint
        
        submission_uuid = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if not move.l10n_ao_fe_serie_id:
             raise UserError(_("A fatura não tem uma Série FE associada."))
        
        serie = move.l10n_ao_fe_serie_id
        series_code = serie.name
        document_no = move.name
        
        jws_software, software_info_detail = self._get_software_signature()
        
        lines = []
        invoice_lines = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        
        for i, line in enumerate(invoice_lines, 1):
            taxes = line.tax_ids
            tax = None
            if taxes:
                taxes = taxes.sorted(key=lambda t: t.amount, reverse=True)
                tax = taxes[0]

            tax_type = 'IVA'
            tax_code = 'NOR'
            tax_percentage = 14.0
            tax_amount = 0.0
            tax_base = line.price_subtotal
            exemption_code = ''
            
            if tax:
                tax_percentage = tax.amount
                tax_amount = self._round_tax((tax_base * tax_percentage) / 100)
                if tax_percentage == 0:
                    tax_code = 'ISE'
                    exemption_code = 'M10' 

            tax_dict = {
                "taxType": tax_type,
                "taxCountryRegion": "AO",
                "taxCode": tax_code,
                "taxPercentage": float(tax_percentage),
                "taxContribution": float(tax_amount)
            }
            if exemption_code:
                tax_dict["taxExemptionCode"] = exemption_code

            line_data = {
                "lineNumber": int(i),
                "productCode": line.product_id.default_code or "S/COD",
                "productDescription": line.name[:200],
                "quantity": float(line.quantity),
                "unitOfMeasure": line.product_uom_id.name or "Un",
                "unitPrice": float(line.price_unit),
                "unitPriceBase": float(line.price_unit),
                "debitAmount": float(line.price_subtotal) if move.move_type in ('out_refund', 'in_invoice') else 0.0,
                "creditAmount": float(line.price_subtotal) if move.move_type in ('out_invoice', 'in_refund') else 0.0,
                "taxes": [tax_dict],
                "settlementAmount": 0.0
            }
            
            # Bloco de Referência para Notas de Crédito (NC) e Notas de Débito (ND)
            doc_type = move.l10n_ao_fe_serie_id.document_class_id.code or "FT"
            if move.move_type == 'out_refund' or doc_type == 'ND':
                origin_move = move.reversed_entry_id
                # Se for ND, o Odoo pode não preencher reversed_entry_id, tentamos debit_origin_id (se existir em versões recentes) ou refs
                if not origin_move and hasattr(move, 'debit_origin_id'):
                    origin_move = move.debit_origin_id
                
                origin_ref = origin_move.name if origin_move else (move.invoice_origin or "Desconhecido")
                
                ref_line_no = "1"
                if origin_move:
                    orig_lines = origin_move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
                    for idx, orig_line in enumerate(orig_lines, 1):
                        if orig_line.product_id == line.product_id:
                            ref_line_no = str(idx)
                            break

                line_data["referenceInfo"] = {
                    "reference": origin_ref,
                    "reason": move.ref or ("Retificação / Débito" if doc_type == 'ND' else "Devolução / Estorno"),
                    "referenceItemLineNo": ref_line_no
                }
                
            lines.append(line_data)

        totals = {
            "taxPayable": float(move.amount_tax),
            "netTotal": float(move.amount_untaxed),
            "grossTotal": float(move.amount_total),
        }

        doc_data = {
            "documentNo": document_no,
            "seriesCode": series_code,
            "documentStatus": "N",
            "documentDate": str(move.invoice_date),
            "documentType": move.l10n_ao_fe_serie_id.document_class_id.code or "FT",
            "systemEntryDate": timestamp,
            "customerTaxID": move.partner_id.vat or "999999999",
            "customerCountry": move.partner_id.country_id.code or "AO",
            "companyName": move.company_id.name,
            "documentTotals": totals,
            "lines": lines
        }
        
        jws_doc = self._get_document_signature(move, doc_data)
        doc_data["jwsDocumentSignature"] = jws_doc

        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": submission_uuid,
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": move.company_id.vat,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "numberOfEntries": 1,
            "documents": [doc_data]
        }

        payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
        
        vals = {
            'fe_submission_uuid': submission_uuid,
            'fe_payload_json': payload_json,
            'fe_jws_software_signature': jws_software,
            'fe_jws_document_signature': jws_doc,
            'fe_document_hash': jws_doc[-4:] if jws_doc else False,
        }
        if not preview:
            vals['fe_sent_datetime'] = fields.Datetime.now()
            
        move.write(vals)

        if preview:
            return payload_json

        self._log_communication(endpoint, 'request', payload_json, move_id=move.id)
        
        try:
            response = self._send_request(url, payload_json)
            resp_json = response.json()
            resp_str = json.dumps(resp_json, indent=2, ensure_ascii=False)
            self._log_communication(endpoint, 'response', payload_json, resp_str, response.status_code, move_id=move.id, request_id=resp_json.get('requestID'))
            return resp_json
        except Exception as e:
            self._log_communication(endpoint, 'error', payload_json, str(e), move_id=move.id)
            raise e

    def registar_recibo(self, payment, preview=False):
        endpoint = "/registarFactura"
        url = self._get_base_url() + endpoint
        
        submission_uuid = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        if not payment.l10n_ao_fe_serie_id:
             raise UserError(_("O recibo não tem uma Série FE associada."))
        
        serie = payment.l10n_ao_fe_serie_id
        series_code = serie.name
        document_no = payment.name
        
        # Nova lógica de cálculo proporcional para Recibos
        invoices = payment.reconciled_invoice_ids
        
        total_tax_payable = 0.0
        total_net = 0.0
        total_gross = payment.amount
        
        source_documents = []
        remaining_amount = payment.amount
        
        if invoices:
            for inv in invoices:
                if remaining_amount <= 0:
                    break
                
                # Tentar encontrar o valor reconciliado para esta fatura
                reconciled_amount = 0.0
                # Em Odoo 14+, as reconciliações estão nas linhas do movimento
                # Procurar nas linhas do pagamento que são de conta a receber/pagar
                payment_lines = payment.move_id.line_ids.filtered(lambda l: l.account_id.account_type in ('asset_receivable', 'liability_payable'))
                
                for line in payment_lines:
                    for partial in line.matched_debit_ids:
                        if partial.debit_move_id.move_id == inv:
                            reconciled_amount += partial.amount
                    for partial in line.matched_credit_ids:
                        if partial.credit_move_id.move_id == inv:
                            reconciled_amount += partial.amount
                
                if reconciled_amount == 0:
                     reconciled_amount = min(remaining_amount, inv.amount_total)

                # Calcular proporção Base/Imposto
                if inv.amount_total > 0:
                    ratio = reconciled_amount / inv.amount_total
                    inv_net_paid = inv.amount_untaxed * ratio
                    inv_tax_paid = self._round_tax(inv.amount_tax * ratio)
                else:
                    inv_net_paid = reconciled_amount
                    inv_tax_paid = 0.0
                
                source_documents.append({
                    "lineNo": int(len(source_documents) + 1),
                    "sourceDocumentID": {
                        "originatingON": inv.name,
                        "documentDate": str(inv.invoice_date)
                    },
                    "creditAmount": float(inv_net_paid)
                })
                
                total_net += inv_net_paid
                total_tax_payable += inv_tax_paid
                remaining_amount -= reconciled_amount
        else:
            # Sem fatura (adiantamento)
            source_documents.append({
                "lineNo": 1,
                "sourceDocumentID": {
                    "originatingON": payment.ref or "Adiantamento",
                    "documentDate": str(payment.date)
                },
                "creditAmount": float(payment.amount)
            })
            total_net = payment.amount

        totals = {
            "taxPayable": float(total_tax_payable),
            "netTotal": float(total_net),
            "grossTotal": float(total_gross)
        }

        payment_receipt = {
            "sourceDocuments": source_documents
        }
        
        doc_data = {
            "documentNo": document_no,
            "documentStatus": "N",
            "documentDate": str(payment.date),
            "documentType": serie.document_class_id.code or "RC",
            "systemEntryDate": timestamp,
            "customerTaxID": payment.partner_id.vat or "999999999",
            "customerCountry": payment.partner_id.country_id.code or "AO",
            "companyName": payment.company_id.name,
            "documentTotals": totals,
            "paymentReceipt": payment_receipt
        }
        
        fields_to_sign = {
            "documentNo": doc_data.get("documentNo"),
            "documentDate": doc_data.get("documentDate"),
            "documentType": doc_data.get("documentType"),
            "companyName": doc_data.get("companyName"),
            "customerTaxID": doc_data.get("customerTaxID"),
            "customerCountry": doc_data.get("customerCountry"),
            "documentTotals": doc_data.get("documentTotals"),
            "taxRegistrationNumber": payment.company_id.vat, 
        }
        jws_doc = self._sign_payload(fields_to_sign, key_type='issuer')
        doc_data["jwsDocumentSignature"] = jws_doc
        
        jws_software, software_info_detail = self._get_software_signature()

        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": submission_uuid,
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": payment.company_id.vat,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "numberOfEntries": 1,
            "documents": [doc_data]
        }
        
        payload_json = json.dumps(payload, indent=2, ensure_ascii=False)
        
        vals = {
            'fe_submission_uuid': submission_uuid,
            'fe_payload_json': payload_json,
            'fe_jws_software_signature': jws_software,
            'fe_jws_document_signature': jws_doc,
            'fe_document_hash': jws_doc[-4:] if jws_doc else False,
        }
        if not preview:
            vals['fe_sent_datetime'] = fields.Datetime.now()
            
        payment.write(vals)

        if preview:
            return payload_json

        self._log_communication(endpoint, 'request', payload_json)
        
        try:
            response = self._send_request(url, payload_json)
            resp_json = response.json()
            resp_str = json.dumps(resp_json, indent=2, ensure_ascii=False)
            self._log_communication(endpoint, 'response', payload_json, resp_str, response.status_code, request_id=resp_json.get('requestID'))
            return resp_json
        except Exception as e:
            self._log_communication(endpoint, 'error', payload_json, str(e))
            raise e

    def obter_estado(self, request_id, tax_registration_number):
        endpoint = "/obterEstado"
        url = self._get_base_url() + endpoint
        
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "requestID": request_id
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        jws_software, software_info_detail = self._get_software_signature()

        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": str(uuid.uuid4()),
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
        _logger.info("OBTER ESTADO PAYLOAD: %s", payload_json)
        self._log_communication(endpoint, 'request', payload_json, request_id=request_id)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def consultar_factura(self, document_no, tax_registration_number):
        endpoint = "/consultarFactura"
        url = self._get_base_url() + endpoint
        
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        jws_software, software_info_detail = self._get_software_signature()
        
        # Campos para assinatura do emissor
        # Baseado no padrão, deve incluir os identificadores principais
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "documentNo": document_no
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": str(uuid.uuid4()),
            "taxRegistrationNumber": tax_registration_number,
            "submissionTimeStamp": timestamp,
            "documentNo": document_no,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "jwsSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        self._log_communication(endpoint, 'request', payload_json)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def solicitar_serie(self, series_type, document_type, requested_quantity, justification, tax_registration_number):
        endpoint = "/solicitarSerie"
        url = self._get_base_url() + endpoint
        
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        current_year = str(datetime.datetime.now().year)
        
        jws_software, software_info_detail = self._get_software_signature()
        
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "timestamp": timestamp
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": str(uuid.uuid4()),
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": tax_registration_number,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "seriesType": series_type,
            "documentType": document_type,
            "seriesYear": int(current_year),
            "establishmentNumber": "0000",
            "seriesContingencyIndicator": "N",
            "requestedQuantity": int(requested_quantity),
            "seriesClass": "NORMAL",
            "justification": justification,
            "jwsIssuerSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        _logger.info("SOLICITAR SERIE PAYLOAD: %s", payload_json)
        self._log_communication(endpoint, 'request', payload_json)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def listar_series(self, tax_registration_number):
        endpoint = "/listarSeries"
        url = self._get_base_url() + endpoint
        
        timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        
        jws_software, software_info_detail = self._get_software_signature()
        
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "timestamp": timestamp
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.2",
            "submissionUUID": str(uuid.uuid4()),
            "submissionTimeStamp": timestamp,
            "taxRegistrationNumber": tax_registration_number,
            "softwareInfo": {
                "softwareInfoDetail": software_info_detail,
                "jwsSoftwareSignature": jws_software
            },
            "jwsIssuerSignature": jws_issuer
        }
        
        payload_json = json.dumps(payload, indent=2)
        self._log_communication(endpoint, 'request', payload_json)
        
        response = self._send_request(url, payload_json)
        return response.json()

    def listar_facturas(self, date_from, date_to, tax_registration_number):
        endpoint = "/listarFacturas"
        url = self._get_base_url() + endpoint
        
        sign_fields = {
            "taxRegistrationNumber": tax_registration_number,
            "queryStartDate": str(date_from),
            "queryEndDate": str(date_to)
        }
        jws_issuer = self._get_issuer_signature(sign_fields)
        
        payload = {
            "schemaVersion": "1.2",
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
