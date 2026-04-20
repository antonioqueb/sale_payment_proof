# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    payment_proof_responsible_user_id = fields.Many2one(
        'res.users',
        string='Responsable de aplicar pagos',
        config_parameter='sale_payment_proof.responsible_user_id',
        help='Usuario al que se le asignará la actividad cuando se cargue '
             'un comprobante de pago en una orden de venta.',
    )
