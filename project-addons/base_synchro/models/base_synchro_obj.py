# See LICENSE file for full copyright and licensing details.

import time

from odoo import api, fields, models


class BaseSynchroServer(models.Model):
    """Class to store the information regarding server."""
    _name = "base.synchro.server"
    _description = "Synchronized server"

    name = fields.Char('Server name', required=True)
    server_url = fields.Char('Server URL', required=True)
    server_port = fields.Integer('Server Port', required=True, default=8069)
    server_db = fields.Char('Server Database', required=True)
    login = fields.Char('User Name', required=True)
    password = fields.Char('Password', required=True)
    obj_ids = fields.One2many('base.synchro.obj', 'server_id', 'Models',
                              ondelete='cascade')

    @api.model
    def sync_databases(self):
        for server in self.search([]):
            wzd = self.env['base.synchro'].\
                create({'server_url': server.id})
            wzd.upload_download()


class BaseSynchroObj(models.Model):
    """Class to store the operations done by wizard."""
    _name = "base.synchro.obj"
    _description = "Register Class"
    _order = 'sequence'

    name = fields.Char('Name', required=True)
    domain = fields.Char('Domain', required=True, default='[]')
    server_id = fields.Many2one('base.synchro.server', 'Server',
                                ondelete='cascade', required=True)
    model_id = fields.Many2one('ir.model', string='Object to synchronize',
                               required=True)
    action = fields.Selection([('d', 'Download'), ('u', 'Upload'),
                               ('b', 'Both')], 'Synchronization direction',
                              required=True,
                              default='d')
    only_create_date = fields.Boolean("Only create date")
    sequence = fields.Integer('Sequence')
    active = fields.Boolean('Active', default=True)
    synchronize_date = fields.Datetime('Latest Synchronization', readonly=True)
    line_id = fields.One2many('base.synchro.obj.line', 'obj_id',
                              'IDs Affected', ondelete='cascade')
    avoid_ids = fields.One2many('base.synchro.obj.avoid', 'obj_id',
                                'Fields Not Sync.')
    context = fields.Text('Context',
                          help="Dictionary format. Used on create/write")

    @api.model
    def get_ids(self, model, dt, domain=None, action=None,
                only_create_date=False, flds=[]):
        if action is None:
            action = {}
        action = action.get('action', 'd')
        pool = self.env[model]
        result = []
        data = []
        get_ids = []
        if dt:
            w_date = domain + [('write_date', '>=', dt)]
            c_date = domain + [('create_date', '>=', dt)]
        else:
            w_date = c_date = domain
        offset = limit = 250
        obj_rec = pool.search(c_date, limit=limit, offset=offset)
        while obj_rec:
            get_ids.extend(obj_rec.ids)
            data.extend(obj_rec.read(flds))
            offset += 250
            obj_rec = pool.search(c_date, limit=limit, offset=offset)
        if not only_create_date:
            if get_ids:
                w_date.append(('id', 'not in', get_ids))
            offset = limit = 250
            obj_rec = pool.search(w_date, limit=limit, offset=offset)
            while obj_rec:
                get_ids.extend(obj_rec.ids)
                data.extend(obj_rec.read(flds))
                offset += 250
                obj_rec = pool.search(w_date, limit=limit, offset=offset)

        for r in data:
            result.append((r['write_date'] or r['create_date'], r['id'],
                           action, r))
        return result


class BaseSynchroObjAvoid(models.Model):
    """Class to avoid the base synchro object."""
    _name = "base.synchro.obj.avoid"
    _description = "Fields to not synchronize"

    name = fields.Char('Field Name', required=True)
    obj_id = fields.Many2one('base.synchro.obj', 'Object', required=True,
                             ondelete='cascade')


class BaseSynchroObjLine(models.Model):
    """Class to store object line in base synchro."""
    _name = "base.synchro.obj.line"
    _description = "Synchronized instances"

    name = fields.Datetime('Date', required=True,
                           default=lambda *args:
                           time.strftime('%Y-%m-%d %H:%M:%S'))
    obj_id = fields.Many2one('base.synchro.obj', 'Object', ondelete='cascade')
    local_id = fields.Integer('Local ID', readonly=True)
    remote_id = fields.Integer('Remote ID', readonly=True)
