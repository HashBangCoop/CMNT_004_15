# See LICENSE file for full copyright and licensing details.

import time
import logging
import threading
from xmlrpc.client import ServerProxy
from odoo import api, fields, models
from odoo.exceptions import Warning
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)


class RPCProxyOne(object):
    def __init__(self, server, ressource):
        """Class to store one RPC proxy server."""
        self.server = server
        local_url = 'http://%s:%d/xmlrpc/common' % (server.server_url,
                                                    server.server_port)
        rpc = ServerProxy(local_url)
        self.uid = rpc.login(server.server_db, server.login, server.password)
        local_url = 'http://%s:%d/xmlrpc/object' % (server.server_url,
                                                    server.server_port)
        self.rpc = ServerProxy(local_url)
        self.ressource = ressource

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.rpc.execute(self.server.server_db,
                                                        self.uid,
                                                        self.server.password,
                                                        self.ressource, name,
                                                        *args)


class RPCProxy(object):
    """Class to store RPC proxy server."""

    def __init__(self, server):
        self.server = server

    def get(self, ressource):
        return RPCProxyOne(self.server, ressource)


class BaseSynchro(models.TransientModel):
    """Base Synchronization."""

    _name = 'base.synchro'

    server_url = fields.Many2one('base.synchro.server', "Server URL",
                                 required=True)
    user_id = fields.Many2one('res.users', "Send Result To",
                              default=lambda self: self.env.user)
    report = []
    report_total = 0
    report_create = 0
    report_write = 0

    @api.model
    def synchronize(self, server, object):
        pool = self
        sync_ids = []
        ctx = self.env.context.copy()
        pool1 = RPCProxy(server)
        pool2 = pool
        dt = object.synchronize_date
        module = pool1.get('ir.module.module')
        model_obj = object.model_id.model
        module_id = module.search([("name", "ilike", "base_synchro"),
                                   ('state', '=', 'installed')])
        if object.context:
            ctx.update(dict(eval(object.context)))
        if not module_id:
            raise Warning(_('''If your Synchronization direction is/
                          download or both, please install
                          "Multi-DB Synchronization" module in targeted/
                        server!'''))
        destination_inverted = False
        if object.action in ('d', 'b'):
            fields_data = pool1.get(object.model_id.model).\
                fields_get()
            for field in object.avoid_ids:
                if field.name in fields_data:
                    del fields_data[field.name]
            flds = list(fields_data.keys())
            sync_ids = pool1.get('base.synchro.obj').\
                get_ids(model_obj, dt, eval(object.domain), {'action': 'd'},
                        object.only_create_date, flds=flds)
            pool_src = pool1
            pool_dest = pool2

        if object.action in ('u', 'b'):
            _logger.debug("Getting ids to synchronize [%s] (%s)",
                          object.synchronize_date, object.domain)
            fields_data = pool2.get(object.model_id.model).\
                fields_get()
            for field in object.avoid_ids:
                if field.name in fields_data:
                    del fields_data[field.name]
            flds = list(fields_data.keys())
            sync_ids += pool2.env['base.synchro.obj'].\
                get_ids(model_obj, dt, eval(object.domain), {'action': 'u'},
                        object.only_create_date, flds=flds)
            pool_src = pool2
            pool_dest = pool1
            destination_inverted = True
        sorted(sync_ids, key=lambda x: str(x[0]))

        _logger.debug("{} REGS no: {}".format(model_obj, len(sync_ids)))
        for dt, id, action, value in sync_ids:
            if action == 'd':
                pool_src = pool1
                pool_dest = pool2
                destination_inverted = False
            else:
                pool_src = pool2
                pool_dest = pool1
                destination_inverted = True
            if 'create_date' in value:
                del value['create_date']
            if 'write_date' in value:
                del value['write_date']
            # Filter fields to not sync
            for field in object.avoid_ids:
                if field.name in value:
                    del value[field.name]

            value = self.data_transform(pool_src, pool_dest,
                                        object.model_id.model, value,
                                        fields_data, action,
                                        destination_inverted)
            id2 = self.get_id(object.id, id, action)
            if id2:
                _logger.debug("Updating model %s [%d]", object.model_id.name,
                              id2)
                if not destination_inverted:
                    pool = pool_dest.env[object.model_id.model].\
                        with_context(ctx)
                    pool.browse([id2]).write(value)
                else:
                    pool_dest.get(object.model_id.model).with_context(ctx).\
                        write([id2], value)
                self.report_total += 1
                self.report_write += 1
            else:
                _logger.debug("Creating model %s", object.model_id.name)
                if not destination_inverted:
                    idnew = pool_dest.env[object.model_id.model].\
                        with_context(ctx).create(value)
                    new_id = idnew.id
                else:
                    idnew = pool_dest.get(object.model_id.model).\
                        with_context(ctx).create(value)
                    new_id = idnew
                self.env['base.synchro.obj.line'].create({
                    'obj_id': object.id,
                    'local_id': (action == 'u') and id or new_id,
                    'remote_id': (action == 'd') and id or new_id
                })
                self.report_total += 1
                self.report_create += 1
        return True

    @api.model
    def get_id(self, object_id, id, action):
        line_pool = self.env['base.synchro.obj.line']
        field_src = (action == 'u') and 'local_id' or 'remote_id'
        field_dest = (action == 'd') and 'local_id' or 'remote_id'
        rid = line_pool.search([('obj_id', '=', object_id),
                                (field_src, '=', id)])
        result = False
        if rid:
            result = line_pool.browse([rid[0].id]).read([field_dest])
            if result:
                result = result[0][field_dest]
        return result

    @api.model
    def relation_transform(self, pool_src, pool_dest, obj_model, res_id,
                           action, destination_inverted):
        if not res_id:
            return False
        _logger.debug("Relation transform")
        self._cr.execute('''select o.id from base_synchro_obj o left join
                        ir_model m on (o.model_id =m.id) where
                        m.model=%s and o.active''', (obj_model,))
        obj = self._cr.fetchone()
        result = False
        if obj:
            result = self.get_id(obj[0], res_id, action)
            _logger.debug("Relation object already synchronized. Getting id%s",
                          result)
        else:
            _logger.debug('''Relation object not synchronized. Searching/
             by name_get and name_search''')
            if not destination_inverted:
                names = pool_src.get(obj_model).name_get([res_id])[0][1]
                res = pool_dest.env[obj_model].name_search(names, [], 'like')
            else:
                pool = pool_src.env[obj_model]
                names = pool.browse([res_id]).name_get()[0][1]
                res = pool_dest.get(obj_model).name_search(names, [], 'like')
            _logger.debug("name_get in src: %s", names)
            _logger.debug("name_search in dest: %s", res)
            if res:
                result = res[0][0]
            else:
                _logger.warning('''Record '%s' on relation %s not found, set/
                                to null.''', names, obj_model)
                _logger.warning('''You should consider synchronize this/
                model '%s''', obj_model)
                self.report.append('''WARNING: Record "%s" on relation %s not/
                    found, set to null.''' % (names, obj_model))
        return result

    @api.model
    def data_transform(self, pool_src, pool_dest, obj, data, fields,
                       action=None, destination_inverted=False):
        if action is None:
            action = {}
        _logger.debug("Transforming data")
        for f in fields:
            ftype = fields[f]['type']
            if ftype in ('function', 'one2many', 'one2one'):
                _logger.debug("Field %s of type %s, discarded.", f, ftype)
                del data[f]
            elif fields[f].get('compute') or fields[f].get('related') or \
                    fields[f].get('depends'):
                _logger.debug("Field %s with compute function, discarded.", f)
                del data[f]
            elif ftype == 'many2one':
                _logger.debug("Field %s is many2one", f)
                if (isinstance(data[f], list)) and data[f]:
                    fdata = data[f][0]
                else:
                    fdata = data[f]
                df = self.relation_transform(pool_src, pool_dest,
                                             fields[f]['relation'], fdata,
                                             action, destination_inverted)
                data[f] = df
                if not data[f]:
                    del data[f]
            elif ftype == 'many2many':
                res = \
                    map(lambda x: self.relation_transform(pool_src,
                        pool_dest,
                        fields[f]['relation'],
                        x, action,
                        destination_inverted),
                        data[f])
                data[f] = [(6, 0, [x for x in res if x])]
        del data['id']
        _logger.debug("Data dest: {}".format(data))
        return data

    @api.multi
    def upload_download(self):
        self.report = []
        start_date = time.strftime('%Y-%m-%d, %Hh %Mm %Ss')
        syn_obj = self.browse(self.ids)[0]
        server = self.env['base.synchro.server'].browse(syn_obj.server_url.id)
        for obj_rec in server.obj_ids:
            _logger.debug("Start synchro of %s", obj_rec.name)
            dt = time.strftime('%Y-%m-%d %H:%M:%S')
            self.synchronize(server, obj_rec)
            if obj_rec.action == 'b':
                time.sleep(1)
                dt = time.strftime('%Y-%m-%d %H:%M:%S')
            obj_rec.write({'synchronize_date': dt})
        end_date = time.strftime('%Y-%m-%d, %Hh %Mm %Ss')

        # Creating res.request for summary results
        if syn_obj.user_id:
            request = self.env['res.request']
            if not self.report:
                self.report.append('No exception.')
            summary = '''Here is the synchronization report:

Synchronization started: %s
Synchronization finished: %s

Synchronized records: %d
Records updated: %d
Records created: %d

Exceptions:
        ''' % (start_date, end_date, self.report_total, self.report_write,
               self.report_create)
            summary += '\n'.join(self.report)
            request.create({
                'name': "Synchronization report",
                'act_from': self.user_id.id,
                'date': time.strftime('%Y-%m-%d, %H:%M:%S'),
                'act_to': syn_obj.user_id.id,
                'body': summary,
            })
            return {}

    @api.multi
    def upload_download_multi_thread(self):
        threaded_synchronization = \
            threading.Thread(target=self.upload_download())
        threaded_synchronization.run()
        id2 = self.env.ref('base_synchro.view_base_synchro_finish').id
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'base.synchro',
            'views': [(id2, 'form')],
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }
