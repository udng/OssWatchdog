# -*- coding: utf-8 -*-

"""
file system monitors
"""

from watchdog.observers import Observer
from watchdog.events import *
from .common import SyncParams
from .common import LocalObject
from .object_manager import ObjectManager
from . import utils
from watchdog.events import EVENT_TYPE_MOVED as EVENT_TYPE_MOVED
from watchdog.events import EVENT_TYPE_CREATED as EVENT_TYPE_CREATED
from watchdog.events import EVENT_TYPE_DELETED as EVENT_TYPE_DELETED
from watchdog.events import EVENT_TYPE_MODIFIED as EVENT_TYPE_MODIFIED

# TODO: add progress reporting system


class SyncCore(FileSystemEventHandler):
    """
    core class representing a local-remote sync link
    """
    def __init__(self, sync_param):
        FileSystemEventHandler.__init__(self)
        self.__sync_param = sync_param
        self.__obj_manager = None
        self.__local_index = None
        self.__is_synchronizing = False
        self.__sync_event_queue = []
        self.__total_task_cnt = 0
        self.__fin_task_cnt = 0

    def initialize(self):
        """
        :return:
        """
        self.__obj_manager = ObjectManager(self.__sync_param.bucket_name)
        self.__local_index = self._local_indexing()
        return self

    def on_moved(self, event):
        """rename"""
        try:
            if self.__is_synchronizing:
                self.__sync_event_queue.append(event)
                return
            remote_old = self.__local_to_remote(event.src_path)
            remote_new = self.__local_to_remote(event.dest_path)
            if self.__obj_manager.object_exists(remote_old):
                self.__obj_manager.rename_object(remote_old, remote_new)
            else:
                # put new file if old file does not exist
                self.__obj_manager.put_object(remote_new, event.dest_path)
        except Exception as e:
            raise e

    # def on_created(self, event):
    #     """create"""
    #     remote = self.__local_to_remote(event.src_path)
    #     self.__obj_manager.put_object(remote, event.src_path)
    #     logger_main.info("file created:{0}".format(event.src_path))

    def on_deleted(self, event):
        """delete"""
        if self.__is_synchronizing:
            self.__sync_event_queue.append(event)
            return
        # FIXME
        # watchdog can't return correct isdir
        # if there is a remote dir, delete it
        # else try delete a file with the same name
        remote_dir = self.__local_to_remote(event.src_path, True)
        if self.__obj_manager.object_exists(remote_dir):
            self.__obj_manager.delete_object(remote_dir)
        else:
            self.__obj_manager.delete_object(remote_dir[:-1])

    def on_modified(self, event):
        """
        modify
        :param event:
        :return:
        """
        if self.__is_synchronizing:
            self.__sync_event_queue.append(event)
            return
        remote = self.__local_to_remote(event.src_path)
        self.__obj_manager.put_object(remote, event.src_path)

    def synchronize(self):
        """
        synchronize local_path with the remote bucket
        :return:
        """
        self.__is_synchronizing = True
        # get remote objects
        remote_iter = self.__obj_manager.get_object_iter(self.__sync_param.remote_path + '/')

        tmp_set = set([])
        for obj in remote_iter:
            local_key = self.__remote_to_local(obj.key)
            if local_key in self.__local_index:   # both have this file
                local_obj = self.__local_index[local_key]
                if local_obj.md5 != self.__obj_manager.get_md5(obj.key):   # different content
                    if local_obj.last_modified >= obj.last_modified:    # local is newer
                        self.__obj_manager.put_object(obj.key, local_key)
                    else:                                               # remote is newer
                        self.__obj_manager.get_object(obj.key, local_key)
            else:
                if utils.remote_isdir(obj.key):
                    if not os.path.exists(local_key):
                        os.makedirs(local_key)
                else:
                    tmp_dir = local_key[:local_key.rfind('\\')]
                    if not os.path.exists(tmp_dir):
                        os.makedirs(tmp_dir)
                    self.__obj_manager.get_object(obj.key, local_key)
            tmp_set.add(local_key)

        for local_key in self.__local_index:
            if local_key not in tmp_set:
                self.__obj_manager.put_object(self.__local_to_remote(local_key), local_key)

        while len(self.__sync_event_queue) > 0:
            event = self.__sync_event_queue.pop(0)
            if event.event_type == EVENT_TYPE_MOVED:
                self.on_moved(event)
            elif event.event_type == EVENT_TYPE_DELETED:
                self.on_deleted(event)
            elif event.event_type == EVENT_TYPE_MODIFIED:
                self.on_modified(event)

        self.__is_synchronizing = False

    def _local_indexing(self):
        """
        generate local file index map {local_path: common.LocalObject}
        :return:
        """
        index_map = self._recursive_indexing(self.__sync_param.local_path, None)
        return index_map

    def _recursive_indexing(self, local_path, index_map):
        if not index_map:
            index_map = {}
        for _dir in os.listdir(local_path):
            abs_dir = os.path.join(local_path, _dir)
            if not os.path.isdir(abs_dir):
                index_map[abs_dir] = LocalObject(abs_dir)
            else:
                index_map[os.path.join(abs_dir, '')] = LocalObject(abs_dir)
                self._recursive_indexing(abs_dir, index_map)
            print(abs_dir)
        return index_map

    def __local_to_remote(self, local_path, is_dir=None):
        """
        transfer local path to the corresponding remote path using directory map
        :param local_path:
        :param is_dir   if None, use os.path.isdir()
        :return:
        """
        local_path = os.path.normpath(local_path)
        root_l = self.__sync_param.local_path
        root_r = self.__sync_param.remote_path
        root_re = root_l.replace('\\', '\\\\')
        pt = re.compile(r"^" + root_re)
        if not pt.match(local_path):
            raise FileNotFoundError('local_path does not belong to this root')

        common = local_path[len(root_l):]
        remote = root_r + common
        if is_dir or os.path.isdir(local_path):
            remote += '/'
        remote = remote.replace('\\', '/')
        return remote

    def __remote_to_local(self, remote_path):
        """
        transfer remote path to the corresponding local path using directory map
        :param remote_path:
        :return:
        """
        remote_path = utils.remote_normpath(remote_path)
        root_l = self.__sync_param.local_path
        root_r = self.__sync_param.remote_path
        pt = re.compile(r"^" + root_r)
        if not pt.match(remote_path):
            raise FileNotFoundError('remote_path does not belong to this root')

        common = remote_path[len(root_r):]
        local = root_l + common
        local = os.path.normpath(local)
        return local

    # def _task_percentage(self, consumed_bytes, total_bytes):
    #     """
    #     progress callback for uploading and downloading files
    #     :param consumed_bytes:
    #     :param total_bytes:
    #     :return:
    #     """
    #     if total_bytes:
    #         rate = int(100 * (float(consumed_bytes) / float(total_bytes)))
    #         sys.stdout.write('\r{0}% '.format(rate))
    #         sys.stdout.flush()
    #
    # def _update_task_cnt(self, fin=False, total=False):
    #     """
    #     update fin and/or total count of tasks
    #     :param fin:
    #     :param total:
    #     :return:
    #     """
    #     if self.__fin_task_cnt == self.__total_task_cnt:
    #         self.__fin_task_cnt = 0
    #         self.__total_task_cnt = 0
    #     if total:
    #         self.__total_task_cnt += 1
    #     if fin:
    #         self.__fin_task_cnt += 1
    #     if self.__fin_task_cnt > self.__total_task_cnt:
    #         self.__fin_task_cnt = self.__total_task_cnt
    #
    # def _show_task_progress(self, discription=''):
    #     """
    #     show task progress
    #     :return:
    #     """
    #     sys.stdout.write('\r' + discription + ' {0}/{1} '.format(self.__fin_task_cnt, self.__total_task_cnt))
    #     sys.stdout.flush()


class Monitor(object):
    """
    a local-remote sync monitor
    """

    def __init__(self, sync_param):
        """
        :param sync_param: should be of type SyncParams
        """
        if sync_param is not SyncParams:
            raise TypeError('sync_param should be of type oss_auto_sync.SyncParams')
        self.__sync_param = sync_param
        self.__core = None
        self.__observer = None

    def initialize(self):
        """
        create sync_socket and init watchdog observer
        :return:
        """
        try:
            self.__core = SyncCore(self.__sync_param).initialize()
            observer = Observer()
            observer.schedule(self.__core, self.__sync_param.local_path, True)
            self.__observer = observer
            return self
        except Exception as e:
            raise e

    def run(self):
        """
        start the observer, synchronize local with remote
        :return:
        """
        try:
            if self.__observer is None:
                raise ValueError("Monitor must be initialized before running")
            self.__observer.start()
            self.__core.synchronize()
        except Exception as e:
            raise e

    def stop(self):
        """
        stop the observer
        :return:
        """
        try:
            # TODO: stop synchronize() as well if is in process
            self.__observer.stop()
            self.__observer.join()
        except Exception as e:
            raise e


class MonitorHub(object):
    """
    collection of Monitors, aim to control them at the same time
    """
    def __init__(self, sync_params):
        """
        :param sync_params: should be an iterable of type SyncParam
        """
        self.__sync_params = sync_params
        self.__monitors = []

    def initialize(self):
        """
        :return:
        """
        try:
            self.__monitors = [Monitor(param).initialize() for param in self.__sync_params]
            return self
        except Exception as e:
            raise e

    def run(self):
        """
        start all monitors
        :return:
        """
        try:
            [monitor.run() for monitor in self.__monitors]
        except Exception as e:
            raise e

    def stop(self):
        """
        stop all monitors
        :return:
        """
        try:
            [monitor.stop() for monitor in self.__monitors]
        except Exception as e:
            raise e
