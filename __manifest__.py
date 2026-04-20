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
}