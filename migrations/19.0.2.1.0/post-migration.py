# -*- coding: utf-8 -*-
def migrate(cr, version):
    """Quita a Sarahi del default de responsables de facturación.

    Solo actualiza el parámetro si sigue con el valor inicial de la v2.0.0
    (Sarahi, Lourdes, Zulema); así no se pisan cambios manuales del admin.
    """
    cr.execute(
        """
        UPDATE ir_config_parameter
           SET value = 'lourdes@somgroup.mx,zulema@somgroup.mx'
         WHERE key = 'sale_payment_proof.invoice_activity_user_logins'
           AND value = 'sarahi@somgroup.mx,lourdes@somgroup.mx,zulema@somgroup.mx'
        """
    )
