/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { FormController } from "@web/views/form/form_controller";
import { useEffect } from "@odoo/owl";

const PPW_MODEL = "sale.payment.proof.upload.wizard";

/**
 * Ensancha el diálogo del wizard "Subir Comprobante de Pago" agregando la clase
 * `o_ppw_modal` al `.modal-dialog`. Respaldo robusto al `:has()` del SCSS; solo
 * actúa sobre este wizard.
 */
patch(FormController.prototype, {
    setup() {
        super.setup();
        if (this.props.resModel === PPW_MODEL) {
            useEffect(
                () => {
                    const forms = document.querySelectorAll(".o_ppw_form");
                    const formEl = forms.length ? forms[forms.length - 1] : null;
                    const modal = formEl ? formEl.closest(".modal-dialog") : null;
                    if (modal) {
                        modal.classList.add("o_ppw_modal");
                    }
                    return () => {
                        if (modal) {
                            modal.classList.remove("o_ppw_modal");
                        }
                    };
                },
                () => []
            );
        }
    },
});
