# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class SalePaymentProof(models.Model):
    _name = 'sale.payment.proof'
    _description = 'Comprobante de Pago'
    _order = 'upload_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Descripción',
        required=True,
        default=lambda self: _('Comprobante de pago'),
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        ondelete='cascade',
        index=True,
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        store=True,
        string='Cliente',
    )
    company_id = fields.Many2one(
        related='sale_order_id.company_id',
        store=True,
    )
    file = fields.Binary(
        string='Archivo',
        required=True,
        attachment=True,
    )
    file_name = fields.Char(string='Nombre del archivo')
    file_mimetype = fields.Char(
        string='Tipo MIME',
        compute='_compute_mimetype',
        store=True,
    )
    is_pdf = fields.Boolean(compute='_compute_mimetype', store=True)
    is_image = fields.Boolean(compute='_compute_mimetype', store=True)
    upload_date = fields.Datetime(
        string='Fecha de carga',
        default=fields.Datetime.now,
        readonly=True,
    )
    uploaded_by = fields.Many2one(
        'res.users',
        string='Subido por',
        default=lambda self: self.env.user,
        readonly=True,
    )
    amount = fields.Monetary(
        string='Monto',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        store=True,
    )
    payment_date = fields.Date(string='Fecha del pago')
    payment_method = fields.Selection(
        [
            ('transfer', 'Transferencia'),
            ('deposit', 'Depósito'),
            ('cash', 'Efectivo'),
            ('check', 'Cheque'),
            ('card', 'Tarjeta'),
            ('other', 'Otro'),
        ],
        string='Método de pago',
        default='transfer',
    )
    reference = fields.Char(string='Referencia / No. de operación')
    notes = fields.Text(string='Notas')
    state = fields.Selection(
        [
            ('pending', 'Pendiente de aplicar'),
            ('applied', 'Aplicado'),
            ('rejected', 'Rechazado'),
        ],
        string='Estado',
        default='pending',
        tracking=True,
    )
    activity_id = fields.Many2one(
        'mail.activity',
        string='Actividad',
        readonly=True,
        copy=False,
    )

    @api.depends('file_name')
    def _compute_mimetype(self):
        image_exts = ('png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp')
        for rec in self:
            mt = ''
            ext = ''
            if rec.file_name and '.' in rec.file_name:
                ext = rec.file_name.lower().rsplit('.', 1)[-1]
            if ext == 'pdf':
                mt = 'application/pdf'
            elif ext in image_exts:
                mt = 'image/' + ('jpeg' if ext == 'jpg' else ext)
            rec.file_mimetype = mt
            rec.is_pdf = (mt == 'application/pdf')
            rec.is_image = mt.startswith('image/')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._post_to_chatter()
            rec._schedule_payment_application_activity()
        return records

    def _post_to_chatter(self):
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        attachment = self.env['ir.attachment'].sudo().search(
            [
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
                ('res_field', '=', 'file'),
            ],
            limit=1,
        )
        new_attachment = False
        if attachment:
            new_attachment = attachment.copy(
                {
                    'res_model': order._name,
                    'res_id': order.id,
                    'res_field': False,
                    'name': self.file_name or self.name or 'comprobante',
                }
            )
        method_label = dict(self._fields['payment_method'].selection).get(
            self.payment_method, ''
        )
        amount_html = ''
        if self.amount:
            amount_html = _('<li><b>Monto:</b> %(amount)s %(cur)s</li>') % {
                'amount': '{:,.2f}'.format(self.amount),
                'cur': self.currency_id.name or '',
            }
        date_html = ''
        if self.payment_date:
            date_html = _('<li><b>Fecha del pago:</b> %s</li>') % self.payment_date
        method_html = ''
        if method_label:
            method_html = _('<li><b>Método:</b> %s</li>') % method_label
        ref_html = ''
        if self.reference:
            ref_html = _('<li><b>Referencia:</b> %s</li>') % self.reference
        notes_html = ''
        if self.notes:
            notes_html = _('<li><b>Notas:</b> %s</li>') % self.notes
        body = _(
            '<p><b>📎 Nuevo comprobante de pago cargado:</b> %(name)s</p>'
            '<ul>%(amount)s%(date)s%(method)s%(ref)s%(notes)s</ul>'
        ) % {
            'name': self.name or '',
            'amount': amount_html,
            'date': date_html,
            'method': method_html,
            'ref': ref_html,
            'notes': notes_html,
        }
        order.message_post(
            body=body,
            attachment_ids=[new_attachment.id] if new_attachment else [],
            subtype_xmlid='mail.mt_note',
        )

    def _get_responsible_user(self):
        ICP = self.env['ir.config_parameter'].sudo()
        user_id_str = ICP.get_param('sale_payment_proof.responsible_user_id', '11')
        try:
            user_id = int(user_id_str)
        except (TypeError, ValueError):
            user_id = 0
        user = self.env['res.users'].browse(user_id).exists()
        if not user:
            user = self.env.user
        return user

    def _schedule_payment_application_activity(self):
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        user = self._get_responsible_user()
        amount_str = '{:,.2f}'.format(self.amount) if self.amount else '—'
        note = _(
            'Se cargó un nuevo comprobante de pago en la orden '
            '<b>%(order)s</b>.<br/>'
            '<b>Cliente:</b> %(partner)s<br/>'
            '<b>Monto:</b> %(amount)s %(currency)s<br/>'
            '<b>Referencia:</b> %(ref)s<br/><br/>'
            'Por favor, valida y aplica el pago en el sistema.'
        ) % {
            'order': order.name,
            'partner': order.partner_id.display_name or '',
            'amount': amount_str,
            'currency': self.currency_id.name or '',
            'ref': self.reference or '—',
        }
        activity = order.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Aplicar pago: %s') % (self.name or ''),
            note=note,
            user_id=user.id,
        )
        if activity:
            self.activity_id = activity.id

    def action_mark_applied(self):
        for rec in self:
            rec.state = 'applied'
            if rec.activity_id and rec.activity_id.exists():
                rec.activity_id.action_feedback(
                    feedback=_('Pago aplicado por %s') % self.env.user.name
                )
        return True

    def action_mark_rejected(self):
        self.write({'state': 'rejected'})
        return True

    def action_mark_pending(self):
        self.write({'state': 'pending'})
        return True

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file/%s?download=false'
            % (self._name, self.id, self.file_name or 'comprobante'),
            'target': 'new',
        }

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s/%s/file/%s?download=true'
            % (self._name, self.id, self.file_name or 'comprobante'),
            'target': 'self',
        }
