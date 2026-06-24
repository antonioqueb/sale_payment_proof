# -*- coding: utf-8 -*-
from markupsafe import Markup

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
        'res.currency',
        string='Divisa',
        default=lambda self: self.env.company.currency_id,
        help='Divisa del pago. Por defecto la de la orden, pero puede '
             'capturarse en otra divisa si el pago se hizo así.',
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
            attachment = rec._post_to_chatter()
            # Clara: aplica el pago (su actividad lleva el comprobante vinculado).
            rec._schedule_payment_application_activity(attachment=attachment)
            # Sarahi / Lourdes / Zulema: generan la factura.
            rec._schedule_invoice_activities(attachment=attachment)
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
        # Markup: en Odoo 17+ message_post escapa los str planos (se vería el HTML
        # como texto). Con Markup se renderiza como HTML.
        order.message_post(
            body=Markup(body),
            attachment_ids=[new_attachment.id] if new_attachment else [],
            subtype_xmlid='mail.mt_note',
        )
        return new_attachment

    # ─── Resolución de responsables (configurable por correo/login) ──────────

    def _resolve_users_by_login(self, logins):
        """Devuelve un recordset res.users a partir de logins/correos.

        Busca primero por login y luego por email. Ignora vacíos y duplicados.
        Resiliente a cambios de id (usa el correo, no el id del usuario).
        """
        Users = self.env['res.users'].sudo()
        found = Users.browse()
        seen = set()
        for raw in (logins or []):
            login = (raw or '').strip()
            if not login or login.lower() in seen:
                continue
            seen.add(login.lower())
            user = Users.search([('login', '=', login)], limit=1)
            if not user:
                user = Users.search([('email', '=', login)], limit=1)
            if user:
                found |= user
        return found

    def _get_responsible_user(self):
        """Compat: responsable de aplicar pagos por id (parámetro antiguo)."""
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

    def _get_payment_apply_user(self):
        """Usuario que APLICA el pago (Clara). Prioriza el correo configurado;
        si no existe, cae al parámetro antiguo por id y, en último caso, al
        usuario actual."""
        ICP = self.env['ir.config_parameter'].sudo()
        login = (ICP.get_param(
            'sale_payment_proof.payment_apply_user_login', 'clara@somgroup.mx'
        ) or '').strip()
        user = self._resolve_users_by_login([login]) if login else self.env['res.users']
        if user:
            return user[:1]
        return self._get_responsible_user()

    def _get_invoice_users(self):
        """Usuarios que CREAN la factura (Sarahi, Lourdes, Zulema)."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param(
            'sale_payment_proof.invoice_activity_user_logins',
            'sarahi@somgroup.mx,lourdes@somgroup.mx,zulema@somgroup.mx',
        )
        logins = [x for x in (raw or '').split(',') if x.strip()]
        return self._resolve_users_by_login(logins)

    # ─── Vínculo visual del comprobante en las actividades ───────────────────

    def _payment_proof_attachment_links(self, attachment):
        """HTML con el link de descarga del comprobante para incluir en la nota
        de la actividad. El documento en sí se vincula como ADJUNTO real de la
        actividad (attachment_ids), que es más fiable que embeber una <img>."""
        if not attachment:
            return ''
        fname = self.file_name or self.name or 'comprobante'
        download_url = '/web/content/%s?download=true&amp;filename=%s' % (
            attachment.id, fname,
        )
        return (
            '<p>📎 <a href="%s" target="_blank"><b>Ver / Descargar comprobante de pago</b></a></p>'
            % download_url
        )

    def _proof_summary_html(self):
        """Encabezado común: cliente, orden, monto y referencia."""
        order = self.sale_order_id
        amount_str = '{:,.2f}'.format(self.amount) if self.amount else '—'
        ref_part = ''
        if self.reference:
            ref_part = _(' (Ref.: %s)') % self.reference
        return _(
            'El cliente <b>%(partner)s</b> registró el pago de la orden '
            '<b>%(order)s</b> por <b>%(amount)s %(currency)s</b>%(ref)s.'
        ) % {
            'partner': order.partner_id.display_name or '',
            'order': order.name,
            'amount': amount_str,
            'currency': self.currency_id.name or '',
            'ref': ref_part,
        }

    # ─── Actividades ─────────────────────────────────────────────────────────

    def _schedule_payment_application_activity(self, attachment=False):
        """Actividad para CLARA: aplicar el pago. Lleva el comprobante vinculado
        (imagen embebida / link de descarga) porque es quien lo aplica."""
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        user = self._get_payment_apply_user()
        if not user:
            return
        note = (
            _('<p><b>📥 Comprobante de pago recibido — aplicar el pago.</b></p>')
            + '<p>' + self._proof_summary_html() + '</p>'
            + _(
                '<p><b>Qué debes hacer:</b> revisa el comprobante adjunto, '
                '<b>registra y aplica el pago</b> en el sistema, y concílialo con '
                'la orden / factura correspondiente. Al terminar, marca esta '
                'actividad como hecha.</p>'
            )
            + self._payment_proof_attachment_links(attachment)
        )
        activity = order.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Aplicar pago: %s') % (order.name or ''),
            note=note,
            user_id=user.id,
        )
        if activity:
            self.activity_id = activity.id
            # Si la versión de Odoo soporta adjuntos en la actividad, se vincula
            # directamente el comprobante (refuerza el "vínculo" pedido).
            if attachment and 'attachment_ids' in activity._fields:
                try:
                    activity.sudo().write({'attachment_ids': [(4, attachment.id)]})
                except Exception:
                    pass

    def _schedule_invoice_activities(self, attachment=False):
        """Actividad 'Crear factura'.

        Odoo solo admite UN responsable por actividad. Por eso se crea UNA sola
        actividad asignada al responsable PRINCIPAL (el primero configurado,
        p. ej. Lourdes) y al resto (p. ej. Zulema) se le agrega como SEGUIDOR de
        la orden y se le NOTIFICA, para que se entere sin duplicar la tarea.
        """
        self.ensure_one()
        order = self.sale_order_id
        if not order:
            return
        users = self._get_invoice_users()
        if not users:
            return

        primary = users[0]
        others = users[1:]

        extra = ''
        if others:
            extra = _(
                '<p><b>Responsable principal:</b> %(primary)s. '
                '<b>También avisada(s):</b> %(others)s. '
                'Cualquiera de ellas puede generar la factura.</p>'
            ) % {
                'primary': primary.name,
                'others': ', '.join(others.mapped('name')),
            }

        note = (
            _('<p><b>🧾 Pago recibido — generar la factura.</b></p>')
            + '<p>' + self._proof_summary_html() + '</p>'
            + _(
                '<p>El comprobante ya está cargado en esta orden (pestaña '
                '«Comprobantes de Pago» y en la conversación / chatter).</p>'
                '<p><b>Qué debes hacer:</b> generar la <b>factura</b> de esta orden '
                'de venta.</p>'
            )
            + extra
            + self._payment_proof_attachment_links(attachment)
        )

        activity = order.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Crear factura: %s') % (order.name or ''),
            note=note,
            user_id=primary.id,
        )

        # Las demás responsables: seguidoras de la orden + aviso en su bandeja.
        other_partners = others.mapped('partner_id')
        if other_partners:
            order.message_subscribe(partner_ids=other_partners.ids)
            order.message_post(
                body=Markup(
                    _('<p>🧾 <b>Pendiente — generar la factura</b> de la orden '
                      '<b>%(order)s</b> (pago recibido).</p>'
                      '<p>Responsable principal: <b>%(primary)s</b>. Te avisamos '
                      'por si necesitas generarla tú; la actividad está en la '
                      'orden de venta.</p>')
                    % {'order': order.name, 'primary': primary.name}
                ),
                partner_ids=other_partners.ids,
                subtype_xmlid='mail.mt_note',
            )
        return activity

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
