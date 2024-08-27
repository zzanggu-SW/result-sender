import os
import pickle
import threading
import time
from datetime import datetime
from multiprocessing import SimpleQueue

from app.analysis.models.mongo_models import ImageDataDocument


# from pymongo import MongoClient


def save_img_predict(save_path_parent, queue: SimpleQueue):
    today = datetime.today().strftime("%Y-%m-%d")
    num = 0
    if os.path.exists(rf"{save_path_parent}/{today}"):
        while os.path.exists(rf"{save_path_parent}/{today}/{num}"):
            num += 1
    else:
        os.makedirs(rf"{save_path_parent}/{today}")

    while True:
        if not queue.empty():
            count, images, predicts, radii, analysis = queue.get()
            print(f"save put {count}")
            save_path = rf"{save_path_parent}/{today}/{num}"
            print(save_path)
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            with open(f"{save_path}/images.pkl", "wb") as f:
                pickle.dump(images, f)
            with open(f"{save_path}/information.pkl", "wb") as f:
                pickle.dump([predicts, radii, analysis], f)

            num += 1
        time.sleep(0.001)


def save_mongo_data(data_save_queue: SimpleQueue):
    # TODO ThreadPool
    # pool = ThreadPool()
    # pool.apply_async
    # client = MongoClient('mongodb://localhost:27017')
    # while True:
    #     images_data = data_save_queue.get()
    #     threading.Thread(target=insert_many, args=(client, images_data,), daemon=True).start()
    while True:
        # collection_idx, images_data = data_save_queue.get()
        images_data = data_save_queue.get()
        threading.Thread(
            target=insert_large_object,
            args=(
                # collection_idx,
                images_data,
            ),
            daemon=True,
        ).start()


# @measure_time('insert_image time')
# def insert_many(client, documents):
#     today = datetime.today().strftime('%Y_%m_%d')
#     collection_idx = documents.pop()

#     # Access a specific database
#     db = client['test_1']

#     # Access a specific collection within the database
#     collection = db[f'{today}_fruit_{collection_idx}_image']

#     collection.insert_many(documents)


# @measure_time('insert_image time')
# def insert_large_object(collection_idx, data):
def insert_large_object(data):
    # today = datetime.today().strftime("%Y_%m_%d")
    img_data_doc = ImageDataDocument(**data)
    # img_data_doc.switch_collection(f'{today}_fruit_{collection_idx}_image')
    img_data_doc.save()
