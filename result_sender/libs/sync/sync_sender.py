from multiprocessing import shared_memory as shm


class SharedCount(shm.SharedMemory):
    def __init__(self, name=None, create=False, size=0, sync_cut_num=4, logger=None, p_name=None):
        super().__init__(name, create, size)
        self.sync_cut_num = sync_cut_num
        self.logger = logger
        self.p_name = p_name

    def test(self):
        self.buf[0] = 1


def shm_count_loader(name="sync_count_shm"):
    try:
        sync_count_shm = SharedCount(name=name)
        print("Found created SharedMemory")
        return sync_count_shm
    except FileNotFoundError:
        print("Waiting to be created SharedMemory")
        sync_count_shm = SharedCount(name=name, create=True, size=10)
        return sync_count_shm
