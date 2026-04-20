## ./__init__.py
```py
from . import models
from . import wizards
```

## ./__manifest__.py
```py
{
    'name': 'Comprobantes de Pago en Órdenes de Venta',
    'version': '19.0.1.0.0',
    'category': 'Sales',
    'summary': 'Gestión de comprobantes de pago con notificación automática al responsable',
    'description': """
Comprobantes de Pago en Órdenes de Venta
=========================================
- Pestaña dedicada en la orden de venta para subir comprobantes de pago.
- Soporta múltiples comprobantes por orden (PDF e imágenes).
- Cada comprobante se publica automáticamente en el chatter como adjunto.
- Crea una actividad para el usuario responsable configurado para que aplique el pago.
    """,
    'author': 'Alphaqueb Consulting SAS',
    'website': 'https://www.alphaqueb.com',
    'license': 'LGPL-3',
    'depends': ['sale_management', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter_data.xml',
        'wizards/sale_payment_proof_upload_wizard_views.xml',
        'views/sale_payment_proof_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sale_payment_proof/static/src/scss/payment_proof.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}```

## ./data/ir_config_parameter_data.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <data noupdate="1">
        <record id="default_payment_proof_responsible_user" model="ir.config_parameter">
            <field name="key">sale_payment_proof.responsible_user_id</field>
            <field name="value">11</field>
        </record>
    </data>
</odoo>
```

## ./models/__init__.py
```py
from . import sale_payment_proof
from . import sale_order
from . import res_config_settings
```

## ./models/res_config_settings.py
```py
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
```

## ./models/sale_order.py
```py
# -*- coding: utf-8 -*-
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
```

## ./models/sale_payment_proof.py
```py
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
```

## ./static/src/scss/payment_proof.scss
```scss
// Sección de comprobantes de pago en sale.order

.o_payment_proof_page {
    .o_pp_header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 16px;
        padding: 16px 20px;
        margin-bottom: 16px;
        background: linear-gradient(135deg, #f8f9fb 0%, #eef1f7 100%);
        border: 1px solid #e3e6ed;
        border-radius: 10px;

        .o_pp_summary {
            display: flex;
            gap: 28px;
            flex-wrap: wrap;

            .o_pp_summary_item {
                display: flex;
                flex-direction: column;
                gap: 2px;

                .o_pp_summary_label {
                    font-size: 11px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                    color: #6c757d;
                    font-weight: 500;
                }
                .o_pp_summary_value {
                    font-size: 18px;
                    font-weight: 600;
                    color: #1f2d3d;
                }
            }
        }

        .o_pp_upload_btn {
            font-size: 15px;
            font-weight: 600;
            padding: 10px 20px;
            border-radius: 8px;
            box-shadow: 0 2px 6px rgba(113, 75, 103, 0.15);
            transition: transform 0.15s ease, box-shadow 0.15s ease;

            &:hover {
                transform: translateY(-1px);
                box-shadow: 0 4px 12px rgba(113, 75, 103, 0.25);
            }
        }

        .o_pp_hint {
            font-size: 13px;
            font-style: italic;
        }
    }
}

// Tarjetas kanban de comprobantes
.o_payment_proof_kanban {
    .o_payment_proof_card {
        display: flex;
        flex-direction: column;
        background: #fff;
        border: 1px solid #e3e6ed;
        border-radius: 10px;
        overflow: hidden;
        transition: box-shadow 0.15s ease, transform 0.15s ease;
        height: 100%;

        &:hover {
            box-shadow: 0 6px 18px rgba(0, 0, 0, 0.08);
            transform: translateY(-2px);
        }

        .o_pp_preview {
            position: relative;
            width: 100%;
            height: 140px;
            background: #f4f6fa;
            display: flex;
            align-items: center;
            justify-content: center;
            border-bottom: 1px solid #e3e6ed;

            .o_pp_thumb {
                max-width: 100%;
                max-height: 100%;
                object-fit: cover;
                width: 100%;
                height: 100%;
            }

            .o_pp_pdf {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 6px;
                color: #c0392b;

                i {
                    font-size: 48px;
                }
                span {
                    font-size: 11px;
                    font-weight: 600;
                    letter-spacing: 1px;
                }
            }

            .o_pp_state {
                position: absolute;
                top: 8px;
                right: 8px;
                font-size: 11px;
                padding: 4px 8px;
                border-radius: 12px;
            }
        }

        .o_pp_body {
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            flex: 1;

            .o_pp_title {
                font-weight: 600;
                font-size: 14px;
                color: #1f2d3d;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .o_pp_amount {
                font-size: 18px;
                font-weight: 700;
                color: #28a745;
            }

            .o_pp_meta {
                display: flex;
                flex-direction: column;
                gap: 3px;
                font-size: 12px;
                color: #6c757d;

                i {
                    width: 14px;
                    margin-right: 4px;
                    color: #9aa3b2;
                }

                .o_pp_uploader {
                    margin-top: 4px;
                    padding-top: 6px;
                    border-top: 1px dashed #e3e6ed;
                    font-size: 11px;
                }
            }
        }
    }
}

// Wizard
.o_pp_wizard_header {
    margin-bottom: 16px;
    padding-bottom: 12px;
    border-bottom: 1px solid #e3e6ed;

    h2 {
        margin: 0 0 4px 0;
        font-size: 20px;
        color: #1f2d3d;
    }
    p {
        margin: 0;
        font-size: 13px;
    }
}
```

## ./views/res_config_settings_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="view_res_config_settings_payment_proof" model="ir.ui.view">
        <field name="name">res.config.settings.payment.proof</field>
        <field name="model">res.config.settings</field>
        <field name="inherit_id" ref="sale.res_config_settings_view_form"/>
        <field name="arch" type="xml">
            <xpath expr="//block[@id='quotations_setting_container']" position="after">
                <block title="Comprobantes de Pago" name="payment_proof_block">
                    <setting id="payment_proof_responsible_setting"
                             string="Responsable de aplicar pagos"
                             help="Usuario que recibirá una actividad cada vez que se cargue un comprobante de pago en una orden de venta.">
                        <field name="payment_proof_responsible_user_id"/>
                    </setting>
                </block>
            </xpath>
        </field>
    </record>

</odoo>
```

## ./views/sale_order_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="view_sale_order_form_payment_proof" model="ir.ui.view">
        <field name="name">sale.order.form.payment.proof</field>
        <field name="model">sale.order</field>
        <field name="inherit_id" ref="sale.view_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//notebook" position="inside">
                <page string="Comprobantes de Pago" name="payment_proofs">
                    <div class="o_payment_proof_page">
                        <div class="o_pp_header">
                            <div class="o_pp_summary">
                                <div class="o_pp_summary_item">
                                    <span class="o_pp_summary_label">Comprobantes</span>
                                    <span class="o_pp_summary_value">
                                        <field name="payment_proof_count" readonly="1"/>
                                    </span>
                                </div>
                                <div class="o_pp_summary_item">
                                    <span class="o_pp_summary_label">Pendientes</span>
                                    <span class="o_pp_summary_value text-warning">
                                        <field name="payment_proof_pending_count" readonly="1"/>
                                    </span>
                                </div>
                                <div class="o_pp_summary_item">
                                    <span class="o_pp_summary_label">Total comprobado</span>
                                    <span class="o_pp_summary_value text-success">
                                        <field name="payment_proof_total" widget="monetary" readonly="1"/>
                                    </span>
                                </div>
                            </div>
                            <button name="action_open_payment_proof_wizard"
                                    type="object"
                                    string="📤 Subir Comprobante"
                                    class="btn btn-primary o_pp_upload_btn"
                                    invisible="not id"/>
                            <div class="o_pp_hint text-muted" invisible="id">
                                <i class="fa fa-info-circle"/>
                                Guarda la orden primero para poder subir comprobantes.
                            </div>
                        </div>
                        <field name="payment_proof_ids"
                               nolabel="1"
                               readonly="1"
                               context="{'default_sale_order_id': id}">
                            <list decoration-success="state == 'applied'"
                                  decoration-danger="state == 'rejected'"
                                  decoration-warning="state == 'pending'">
                                <field name="upload_date"/>
                                <field name="name"/>
                                <field name="amount" widget="monetary" sum="Total"/>
                                <field name="currency_id" column_invisible="1"/>
                                <field name="payment_date"/>
                                <field name="payment_method"/>
                                <field name="reference"/>
                                <field name="uploaded_by"/>
                                <field name="state"/>
                                <button name="action_preview"
                                        type="object"
                                        icon="fa-eye"
                                        title="Ver comprobante"/>
                                <button name="action_download"
                                        type="object"
                                        icon="fa-download"
                                        title="Descargar"/>
                            </list>
                        </field>
                    </div>
                </page>
            </xpath>
        </field>
    </record>

</odoo>```

## ./views/sale_payment_proof_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- Vista Form -->
    <record id="view_sale_payment_proof_form" model="ir.ui.view">
        <field name="name">sale.payment.proof.form</field>
        <field name="model">sale.payment.proof</field>
        <field name="arch" type="xml">
            <form string="Comprobante de Pago">
                <header>
                    <button name="action_mark_applied"
                            string="Marcar como aplicado"
                            type="object"
                            class="oe_highlight"
                            invisible="state == 'applied'"/>
                    <button name="action_mark_rejected"
                            string="Rechazar"
                            type="object"
                            invisible="state == 'rejected'"/>
                    <button name="action_mark_pending"
                            string="Volver a pendiente"
                            type="object"
                            invisible="state == 'pending'"/>
                    <field name="state" widget="statusbar" statusbar_visible="pending,applied"/>
                </header>
                <sheet>
                    <div class="oe_button_box" name="button_box">
                        <button name="action_preview"
                                type="object"
                                class="oe_stat_button"
                                icon="fa-eye"
                                invisible="not file">
                            <span class="o_stat_text">Ver</span>
                        </button>
                        <button name="action_download"
                                type="object"
                                class="oe_stat_button"
                                icon="fa-download"
                                invisible="not file">
                            <span class="o_stat_text">Descargar</span>
                        </button>
                    </div>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1>
                            <field name="name" placeholder="Descripción del comprobante"/>
                        </h1>
                    </div>
                    <group>
                        <group>
                            <field name="sale_order_id" readonly="1"/>
                            <field name="partner_id" readonly="1"/>
                            <field name="amount" widget="monetary"/>
                            <field name="currency_id" invisible="1"/>
                            <field name="payment_date"/>
                            <field name="payment_method"/>
                            <field name="reference"/>
                        </group>
                        <group>
                            <field name="file" filename="file_name" widget="binary"/>
                            <field name="file_name" invisible="1"/>
                            <field name="file_mimetype" invisible="1"/>
                            <field name="is_pdf" invisible="1"/>
                            <field name="is_image" invisible="1"/>
                            <field name="upload_date"/>
                            <field name="uploaded_by"/>
                            <field name="activity_id" invisible="1"/>
                        </group>
                    </group>
                    <group string="Notas">
                        <field name="notes" nolabel="1" placeholder="Notas adicionales..."/>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <!-- Vista List -->
    <record id="view_sale_payment_proof_list" model="ir.ui.view">
        <field name="name">sale.payment.proof.list</field>
        <field name="model">sale.payment.proof</field>
        <field name="arch" type="xml">
            <list string="Comprobantes de Pago"
                  decoration-success="state == 'applied'"
                  decoration-danger="state == 'rejected'"
                  decoration-warning="state == 'pending'">
                <field name="upload_date"/>
                <field name="name"/>
                <field name="sale_order_id"/>
                <field name="partner_id"/>
                <field name="amount" widget="monetary" sum="Total"/>
                <field name="currency_id" column_invisible="1"/>
                <field name="payment_date"/>
                <field name="payment_method"/>
                <field name="reference"/>
                <field name="uploaded_by"/>
                <field name="state"/>
            </list>
        </field>
    </record>

    <!-- Vista Kanban (minimalista Odoo 19) -->
    <record id="view_sale_payment_proof_kanban" model="ir.ui.view">
        <field name="name">sale.payment.proof.kanban</field>
        <field name="model">sale.payment.proof</field>
        <field name="arch" type="xml">
            <kanban default_order="upload_date desc">
                <templates>
                    <t t-name="card">
                        <div class="o_payment_proof_card">
                            <div class="o_pp_preview">
                                <t t-if="record.is_image.raw_value">
                                    <img t-att-src="'/web/image/sale.payment.proof/' + record.id.raw_value + '/file'"
                                         alt="Comprobante"
                                         class="o_pp_thumb"/>
                                </t>
                                <t t-elif="record.is_pdf.raw_value">
                                    <div class="o_pp_pdf">
                                        <i class="fa fa-file-pdf-o"/>
                                        <span>PDF</span>
                                    </div>
                                </t>
                                <t t-else="">
                                    <div class="o_pp_pdf">
                                        <i class="fa fa-file-o"/>
                                    </div>
                                </t>
                            </div>
                            <div class="o_pp_body">
                                <div class="o_pp_title">
                                    <field name="name"/>
                                </div>
                                <div class="o_pp_amount">
                                    <field name="amount" widget="monetary"/>
                                </div>
                                <div class="o_pp_meta">
                                    <div>
                                        <field name="state"/>
                                    </div>
                                    <div>
                                        <i class="fa fa-calendar"/> <field name="payment_date"/>
                                    </div>
                                    <div>
                                        <i class="fa fa-credit-card"/> <field name="payment_method"/>
                                    </div>
                                    <div>
                                        <i class="fa fa-hashtag"/> <field name="reference"/>
                                    </div>
                                    <div class="o_pp_uploader">
                                        <i class="fa fa-user"/> <field name="uploaded_by"/> · <field name="upload_date"/>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </t>
                </templates>
            </kanban>
        </field>
    </record>

    <!-- Vista Search (minimalista, sin uid, sin group_by) -->
    <record id="view_sale_payment_proof_search" model="ir.ui.view">
        <field name="name">sale.payment.proof.search</field>
        <field name="model">sale.payment.proof</field>
        <field name="arch" type="xml">
            <search>
                <field name="name"/>
                <field name="sale_order_id"/>
                <field name="partner_id"/>
                <field name="reference"/>
                <filter name="filter_pending" string="Pendientes" domain="[('state', '=', 'pending')]"/>
                <filter name="filter_applied" string="Aplicados" domain="[('state', '=', 'applied')]"/>
                <filter name="filter_rejected" string="Rechazados" domain="[('state', '=', 'rejected')]"/>
            </search>
        </field>
    </record>

    <!-- Acción menú -->
    <record id="action_sale_payment_proof" model="ir.actions.act_window">
        <field name="name">Comprobantes de Pago</field>
        <field name="res_model">sale.payment.proof</field>
        <field name="view_mode">kanban,list,form</field>
        <field name="context">{'search_default_filter_pending': 1}</field>
    </record>

    <menuitem id="menu_sale_payment_proof"
              name="Comprobantes de Pago"
              parent="sale.sale_order_menu"
              action="action_sale_payment_proof"
              sequence="25"/>

</odoo>```

## ./wizards/__init__.py
```py
from . import sale_payment_proof_upload_wizard
```

## ./wizards/sale_payment_proof_upload_wizard.py
```py
# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalePaymentProofUploadWizard(models.TransientModel):
    _name = 'sale.payment.proof.upload.wizard'
    _description = 'Asistente para subir comprobantes de pago'

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta',
        required=True,
        readonly=True,
    )
    partner_id = fields.Many2one(
        related='sale_order_id.partner_id',
        string='Cliente',
        readonly=True,
    )
    currency_id = fields.Many2one(
        related='sale_order_id.currency_id',
        readonly=True,
    )
    name = fields.Char(
        string='Descripción',
        default=lambda self: _('Comprobante de pago'),
        required=True,
    )
    file = fields.Binary(string='Archivo', required=True)
    file_name = fields.Char(string='Nombre del archivo')
    amount = fields.Monetary(
        string='Monto',
        currency_field='currency_id',
    )
    payment_date = fields.Date(
        string='Fecha del pago',
        default=fields.Date.context_today,
    )
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
    add_another = fields.Boolean(
        string='Subir otro comprobante después de guardar',
        default=False,
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_('Debes adjuntar un archivo.'))
        proof = self.env['sale.payment.proof'].create(
            {
                'sale_order_id': self.sale_order_id.id,
                'name': self.name or _('Comprobante'),
                'file': self.file,
                'file_name': self.file_name or self.name,
                'amount': self.amount,
                'payment_date': self.payment_date,
                'payment_method': self.payment_method,
                'reference': self.reference,
                'notes': self.notes,
            }
        )
        if self.add_another:
            return self.sale_order_id.action_open_payment_proof_wizard()
        return {'type': 'ir.actions.act_window_close'}
```

## ./wizards/sale_payment_proof_upload_wizard_views.xml
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="view_sale_payment_proof_upload_wizard_form" model="ir.ui.view">
        <field name="name">sale.payment.proof.upload.wizard.form</field>
        <field name="model">sale.payment.proof.upload.wizard</field>
        <field name="arch" type="xml">
            <form string="Subir Comprobante de Pago">
                <sheet>
                    <div class="o_pp_wizard_header">
                        <h2>📤 Subir Comprobante de Pago</h2>
                        <p class="text-muted">
                            Carga el comprobante para la orden
                            <field name="sale_order_id" readonly="1" class="oe_inline" nolabel="1"/>
                            del cliente
                            <field name="partner_id" readonly="1" class="oe_inline" nolabel="1"/>.
                        </p>
                    </div>
                    <group>
                        <group>
                            <field name="name"/>
                            <field name="file" filename="file_name" widget="binary" required="1"/>
                            <field name="file_name" invisible="1"/>
                            <field name="currency_id" invisible="1"/>
                        </group>
                        <group>
                            <field name="amount" widget="monetary"/>
                            <field name="payment_date"/>
                            <field name="payment_method"/>
                            <field name="reference"/>
                        </group>
                    </group>
                    <group string="Notas">
                        <field name="notes" nolabel="1" placeholder="Notas opcionales sobre este comprobante..."/>
                    </group>
                    <group>
                        <field name="add_another"/>
                    </group>
                </sheet>
                <footer>
                    <button name="action_confirm"
                            string="Subir Comprobante"
                            type="object"
                            class="btn-primary"/>
                    <button string="Cancelar"
                            class="btn-secondary"
                            special="cancel"/>
                </footer>
            </form>
        </field>
    </record>

</odoo>
```

