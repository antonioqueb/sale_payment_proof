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
    payment_proof_apply_user_login = fields.Char(
        string='Responsable de aplicar el pago (correo/login)',
        config_parameter='sale_payment_proof.payment_apply_user_login',
        help='Correo o login del usuario que aplica el pago (p. ej. Clara). '
             'Su actividad incluye el comprobante vinculado. Tiene prioridad '
             'sobre el "Responsable de aplicar pagos" por id.',
    )
    payment_proof_invoice_user_logins = fields.Char(
        string='Responsables de crear factura (correos/logins, separados por coma)',
        config_parameter='sale_payment_proof.invoice_activity_user_logins',
        help='Correos o logins de los usuarios que generan la factura '
             '(p. ej. Sarahi, Lourdes, Zulema). Se crea una actividad '
             '"Crear factura" idéntica para cada uno.',
    )
