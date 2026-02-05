/** @odoo-module */

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

if (Order && Order.prototype) {
    patch(Order.prototype, {
        export_for_printing() {
            const result = super.export_for_printing(...arguments);
            try {
                if (this.l10n_ao_fe_hash) {
                    result.fe_document_hash = this.l10n_ao_fe_hash;
                }
                if (this.l10n_ao_fe_qr_code) {
                    result.fe_qr_code = this.l10n_ao_fe_qr_code;
                }
            } catch (e) {
                console.error("Error in l10n_ao_fe POS patch:", e);
            }
            return result;
        }
    });
}
