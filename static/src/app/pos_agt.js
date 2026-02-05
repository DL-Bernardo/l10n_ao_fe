/** @odoo-module */

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";

patch(Order.prototype, {
    export_for_printing() {
        const result = super.export_for_printing(...arguments);
        
        // Se a ordem foi faturada, tentamos obter os dados da fatura associada
        // No Odoo 17, o objeto 'order' pode ter campos sincronizados do backend
        if (this.l10n_ao_fe_hash) {
            result.fe_document_hash = this.l10n_ao_fe_hash;
        }
        if (this.l10n_ao_fe_qr_code) {
            result.fe_qr_code = this.l10n_ao_fe_qr_code;
        }
        
        return result;
    },
    
    // Garantir que os dados são lidos quando a ordem é carregada ou devolvida pelo servidor
    init_from_JSON(json) {
        super.init_from_JSON(...arguments);
        this.l10n_ao_fe_hash = json.l10n_ao_fe_hash || null;
        this.l10n_ao_fe_qr_code = json.l10n_ao_fe_qr_code || null;
    }
});
