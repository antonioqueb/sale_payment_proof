# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    payment_proof_ids = fields.One2many(
        'sale.payment.proof',
        'sale_order_id',
        string='Comprobantes de Pago',
    )
    payment_proof_count = fields.Integer(
        string='Comprobantes',
        compute='_compute_payment_proof_summary',
    )
    payment_proof_total = fields.Monetary(
        string='Total comprobado',
        compute='_compute_payment_proof_summary',
        currency_field='currency_id',
    )
    payment_proof_pending_count = fields.Integer(
        string='Pendientes',
        compute='_compute_payment_proof_summary',
    )

    @api.depends(
        'payment_proof_ids',
        'payment_proof_ids.amount',
        'payment_proof_ids.state',
    )
    def _compute_payment_proof_summary(self):
        for order in self:
            proofs = order.payment_proof_ids
            order.payment_proof_count = len(proofs)
            order.payment_proof_total = sum(proofs.mapped('amount'))
            order.payment_proof_pending_count = len(
                proofs.filtered(lambda p: p.state == 'pending')
            )

    def action_open_payment_proof_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subir comprobante de pago'),
            'res_model': 'sale.payment.proof.upload.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_sale_order_id': self.id,
            },
        }

    # =========================================================================
    # MOTOR UNIFICADO DE AVISOS DE "PAGO RECIBIDO"
    #
    # Centraliza, a nivel de la ORDEN, los avisos por un pago recibido (sea
    # transferencia/efectivo/mixto). Lo usan tanto sale.payment.proof como
    # cash.receipt (efectivo) y el registro unificado de pagos, para NO duplicar
    # la lógica. Crea:
    #   - Actividad "Aplicar pago" (Clara) con el/los comprobante(s) vinculados.
    #   - Actividad "Crear factura" (Lourdes; Zulema avisada).
    #   - (opcional) Resumen en el chatter de la orden.
    # Responsables configurables por correo/login (Ajustes → Ventas).
    # =========================================================================

    def _pp_resolve_users_by_login(self, logins):
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

    def _pp_get_payment_apply_user(self):
        """Usuario que APLICA el pago (Clara). Prioriza el correo configurado;
        si no existe, cae al parámetro antiguo por id y al usuario actual."""
        ICP = self.env['ir.config_parameter'].sudo()
        login = (ICP.get_param(
            'sale_payment_proof.payment_apply_user_login', 'clara@somgroup.mx'
        ) or '').strip()
        user = self._pp_resolve_users_by_login([login]) if login else self.env['res.users']
        if user:
            return user[:1]
        uid_str = ICP.get_param('sale_payment_proof.responsible_user_id', '0')
        try:
            uid = int(uid_str)
        except (TypeError, ValueError):
            uid = 0
        return self.env['res.users'].browse(uid).exists() or self.env.user

    def _pp_get_invoice_users(self):
        """Usuarios que CREAN la factura (Lourdes, Zulema)."""
        ICP = self.env['ir.config_parameter'].sudo()
        raw = ICP.get_param(
            'sale_payment_proof.invoice_activity_user_logins',
            'lourdes@somgroup.mx,zulema@somgroup.mx',
        )
        logins = [x for x in (raw or '').split(',') if x.strip()]
        return self._pp_resolve_users_by_login(logins)

    def _pp_amount_label(self, amount, currency):
        try:
            amt = '{:,.2f}'.format(amount or 0.0)
        except (ValueError, TypeError):
            amt = str(amount or '')
        cur = currency.name if currency else ''
        return ('%s %s' % (amt, cur)).strip()

    def _pp_payment_summary_html(self, amount, currency, method_label='', reference=''):
        self.ensure_one()
        ref_part = (_(' (Ref.: %s)') % reference) if reference else ''
        method_part = (_(' por %s') % method_label) if method_label else ''
        return _(
            'El cliente <b>%(partner)s</b> registró un pago%(method)s de '
            '<b>%(amount)s</b> para la orden <b>%(order)s</b>%(ref)s.'
        ) % {
            'partner': self.partner_id.display_name or '',
            'method': method_part,
            'amount': self._pp_amount_label(amount, currency),
            'order': self.name,
            'ref': ref_part,
        }

    def _pp_attachments_links_html(self, attachments):
        if not attachments:
            return ''
        parts = []
        for att in attachments:
            name = att.name or 'comprobante'
            url = '/web/content/%s?download=true&amp;filename=%s' % (att.id, name)
            parts.append(
                '<p>📎 <a href="%s" target="_blank"><b>Ver / Descargar: %s</b></a></p>'
                % (url, name)
            )
        return ''.join(parts)

    def _payment_received_notify(self, amount=0.0, currency=None, method_label='',
                                 reference='', notes='', attachments=None,
                                 post_chatter=True, extra_summary_html=''):
        """Crea los avisos de pago recibido. Devuelve la actividad de Clara
        (aplicar pago) por si el documento llamador quiere vincularla."""
        self.ensure_one()
        attachments = attachments or self.env['ir.attachment']
        summary = self._pp_payment_summary_html(amount, currency, method_label, reference)
        links = self._pp_attachments_links_html(attachments)

        # 1) Resumen en el chatter de la orden (opcional).
        if post_chatter:
            notes_html = ('<p><b>Notas:</b> %s</p>' % notes) if notes else ''
            self.message_post(
                body=Markup('<p>💳 ' + summary + '</p>' + extra_summary_html + notes_html + links),
                attachment_ids=attachments.ids,
                subtype_xmlid='mail.mt_note',
            )

        # 2) Actividad "Aplicar pago" (Clara).
        apply_activity = False
        apply_user = self._pp_get_payment_apply_user()
        if apply_user:
            note = (
                _('<p><b>📥 Pago recibido — aplicar el pago.</b></p>')
                + '<p>' + summary + '</p>' + extra_summary_html
                + _('<p><b>Qué debes hacer:</b> revisa el/los comprobante(s), '
                    '<b>registra y aplica el pago</b> en el sistema y concílialo con '
                    'la orden / factura. Al terminar, marca esta actividad como hecha.</p>')
                + links
            )
            apply_activity = self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Aplicar pago: %s') % (self.name or ''),
                note=note,
                user_id=apply_user.id,
            )
            if apply_activity and attachments and 'attachment_ids' in apply_activity._fields:
                try:
                    apply_activity.sudo().write(
                        {'attachment_ids': [(4, a.id) for a in attachments]}
                    )
                except Exception:
                    pass

        # 3) Actividad "Crear factura" (Lourdes; Zulema avisada).
        inv_users = self._pp_get_invoice_users()
        if inv_users:
            primary = inv_users[0]
            others = inv_users[1:]
            extra = ''
            if others:
                extra = _(
                    '<p><b>Responsable principal:</b> %(primary)s. '
                    '<b>También avisada(s):</b> %(others)s. '
                    'Cualquiera puede generar la factura.</p>'
                ) % {'primary': primary.name, 'others': ', '.join(others.mapped('name'))}
            note = (
                _('<p><b>🧾 Pago recibido — generar la factura.</b></p>')
                + '<p>' + summary + '</p>' + extra_summary_html
                + _('<p>El/los comprobante(s) ya están en la orden (chatter y pestañas).</p>'
                    '<p><b>Qué debes hacer:</b> generar la <b>factura</b> de esta orden.</p>')
                + extra + links
            )
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Crear factura: %s') % (self.name or ''),
                note=note,
                user_id=primary.id,
            )
            other_partners = others.mapped('partner_id')
            if other_partners:
                self.message_subscribe(partner_ids=other_partners.ids)
                self.message_post(
                    body=Markup(
                        _('<p>🧾 <b>Pendiente — generar la factura</b> de la orden '
                          '<b>%(order)s</b> (pago recibido). Responsable principal: '
                          '<b>%(primary)s</b>.</p>')
                        % {'order': self.name, 'primary': primary.name}
                    ),
                    partner_ids=other_partners.ids,
                    subtype_xmlid='mail.mt_note',
                )

        return apply_activity

    def _pp_has_registered_payment(self):
        """True si la orden ya tiene factura(s) con pago registrado (total o
        parcial). Sirve para resaltar el saldo pendiente al cobrar un excedente."""
        self.ensure_one()
        paid_states = {'in_payment', 'paid', 'partial', 'reversed'}
        invoices = self.invoice_ids.filtered(lambda m: m.state == 'posted')
        return any((inv.payment_state in paid_states) for inv in invoices)

    def _overcharge_notify(self, product_name='', over_qty=0.0, uom_name='',
                           amount=None, reason=''):
        """Avisa a FACTURACIÓN (Lourdes/Zulema) y COBRANZA (Clara) cuando se
        decide COBRAR un excedente sobre lo solicitado (p. ej. desde Transit
        Allocation). Reutiliza los mismos responsables del flujo de pagos.

        Si ya hay un pago/factura registrado, resalta el SALDO PENDIENTE que
        genera el aumento del monto, que es el caso más crítico."""
        self.ensure_one()

        has_payment = self._pp_has_registered_payment()
        qty_label = ('%.2f %s' % (over_qty or 0.0, uom_name or '')).strip()
        amount_label = self._pp_amount_label(amount, self.currency_id) if amount else ''

        summary = _(
            'En la orden <b>%(order)s</b> (cliente <b>%(partner)s</b>) se decidió '
            '<b>COBRAR un excedente</b> sobre lo solicitado'
        ) % {'order': self.name, 'partner': self.partner_id.display_name or ''}
        if product_name:
            summary += _(' del producto <b>%s</b>') % product_name
        summary += _(': <b>%(qty)s</b>%(amount)s.') % {
            'qty': qty_label,
            'amount': (_(' (~%s)') % amount_label) if amount_label else '',
        }

        new_total_html = _('<p>Nuevo total de la orden: <b>%s</b>.</p>') % (
            self._pp_amount_label(self.amount_total, self.currency_id)
        )

        if has_payment:
            balance_html = _(
                '<p>⚠️ <b>La orden ya tiene un pago/factura registrado.</b> Al subir '
                'el monto, queda un <b>saldo pendiente</b>: hay que ajustar/emitir la '
                'factura por el excedente y dar seguimiento al cobro del saldo.</p>'
            )
        else:
            balance_html = _(
                '<p>Aún no hay pago registrado; queda anotado para que el cobro y la '
                'facturación consideren el monto actualizado.</p>'
            )

        reason_html = ('<p><b>Motivo:</b> %s</p>' % reason) if reason else ''

        # Chatter de la orden
        self.message_post(
            body=Markup('<p>💰 ' + summary + '</p>' + new_total_html + balance_html + reason_html),
            subtype_xmlid='mail.mt_note',
        )

        # COBRANZA (Clara): seguimiento del cobro del saldo.
        apply_user = self._pp_get_payment_apply_user()
        if apply_user:
            note = (
                _('<p><b>💰 Excedente a cobrar — cobranza.</b></p>')
                + '<p>' + summary + '</p>' + new_total_html + balance_html
                + _('<p><b>Qué debes hacer:</b> da seguimiento al <b>cobro del saldo</b> '
                    'generado por este excedente y concílialo cuando se reciba.</p>')
                + reason_html
            )
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Cobrar excedente: %s') % (self.name or ''),
                note=note,
                user_id=apply_user.id,
            )

        # FACTURACIÓN (Lourdes/Zulema): emitir/ajustar la factura del excedente.
        inv_users = self._pp_get_invoice_users()
        if inv_users:
            primary = inv_users[0]
            others = inv_users[1:]
            extra = ''
            if others:
                extra = _(
                    '<p><b>Responsable principal:</b> %(primary)s. '
                    '<b>También avisada(s):</b> %(others)s.</p>'
                ) % {'primary': primary.name, 'others': ', '.join(others.mapped('name'))}
            note = (
                _('<p><b>🧾 Excedente a cobrar — facturación.</b></p>')
                + '<p>' + summary + '</p>' + new_total_html + balance_html
                + _('<p><b>Qué debes hacer:</b> emitir o <b>ajustar la factura</b> para '
                    'incluir el excedente cobrado.</p>')
                + extra + reason_html
            )
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                summary=_('Facturar excedente: %s') % (self.name or ''),
                note=note,
                user_id=primary.id,
            )
            other_partners = others.mapped('partner_id')
            if other_partners:
                self.message_subscribe(partner_ids=other_partners.ids)
                self.message_post(
                    body=Markup(
                        _('<p>🧾 <b>Excedente a cobrar</b> en la orden <b>%(order)s</b>: '
                          'revisar/ajustar la factura. Responsable principal: '
                          '<b>%(primary)s</b>.</p>')
                        % {'order': self.name, 'primary': primary.name}
                    ),
                    partner_ids=other_partners.ids,
                    subtype_xmlid='mail.mt_note',
                )
        return True

    def _credit_note_request_notify(self, product_name='', qty=0.0, uom_name='', reason=''):
        """Avisa a FACTURACIÓN (Lourdes/Zulema) que se solicitó una NOTA DE
        CRÉDITO para que la generen. Reutiliza los responsables del flujo de
        pagos (mismo equipo de facturación)."""
        self.ensure_one()
        inv_users = self._pp_get_invoice_users()
        if not inv_users:
            return False

        detail = ''
        if product_name:
            detail = _(' (%(p)s: %(qty)s %(uom)s)') % {
                'p': product_name,
                'qty': ('%.2f' % (qty or 0.0)),
                'uom': uom_name or '',
            }
        summary = _(
            'Se solicitó generar una <b>nota de crédito</b> para la orden '
            '<b>%(order)s</b> (cliente <b>%(partner)s</b>)%(detail)s.'
        ) % {
            'order': self.name,
            'partner': self.partner_id.display_name or '',
            'detail': detail,
        }
        reason_html = ('<p><b>Motivo:</b> %s</p>' % reason) if reason else ''

        self.message_post(
            body=Markup('<p>🧾 ' + summary + '</p>' + reason_html),
            subtype_xmlid='mail.mt_note',
        )

        primary = inv_users[0]
        others = inv_users[1:]
        extra = ''
        if others:
            extra = _(
                '<p><b>Responsable principal:</b> %(primary)s. '
                '<b>También avisada(s):</b> %(others)s.</p>'
            ) % {'primary': primary.name, 'others': ', '.join(others.mapped('name'))}
        note = (
            _('<p><b>🧾 Generar nota de crédito.</b></p>')
            + '<p>' + summary + '</p>'
            + _('<p><b>Qué debes hacer:</b> generar la <b>nota de crédito</b> '
                'correspondiente en el sistema contable.</p>')
            + extra + reason_html
        )
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            summary=_('Generar nota de crédito: %s') % (self.name or ''),
            note=note,
            user_id=primary.id,
        )
        other_partners = others.mapped('partner_id')
        if other_partners:
            self.message_subscribe(partner_ids=other_partners.ids)
            self.message_post(
                body=Markup(
                    _('<p>🧾 <b>Generar nota de crédito</b> para la orden '
                      '<b>%(order)s</b>. Responsable principal: <b>%(primary)s</b>.</p>')
                    % {'order': self.name, 'primary': primary.name}
                ),
                partner_ids=other_partners.ids,
                subtype_xmlid='mail.mt_note',
            )
        return True
