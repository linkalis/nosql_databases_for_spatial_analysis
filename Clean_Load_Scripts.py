## Extract, Clean, and Load Data Scripts

# Import required libraries
import os, fnmatch
import json
from bson import ObjectId
import pprint
import time

# Libraries for Mongo
import pymongo
from bson import Binary, Code
from bson.json_util import dumps

# Libraries for Neo4j
from neo4j.v1 import GraphDatabase
from neo4j.v1 import exceptions

# Libraries for ElasticSearch
from elasticsearch import Elasticsearch

# Geohashing
# http://www.willmcginnis.com/2016/01/16/pygeohash-1-0-1-fast-gis-geohash-python/
import pygeohash as pgh

# Import database passwords
import secrets

## Extractor

class Extractor:
    ''' Takes a folder name and a logs directory path and initializes a log file containing the name of
    every file in the target folder.  Contains methods for checking which files in the log have not yet
    been loaded and getting and reading in the next available file. '''

    def __init__(self, data_path, logs_path, initialize=True):
        self.data_path = data_path
        self.logs_path = logs_path

        # Create a directory to store the log files, if necessary
        logs_dir = os.path.dirname(self.logs_path)
        if not os.path.exists(logs_dir):
            os.makedirs(logs_dir)

        # If we're in the initialize state, create a 'files_to_load.txt' file,
        # then write the name of every file in the directory to this file
        if initialize:
            files_to_load_log  = open(self.logs_path + "/files_to_load.txt", "w")
            data_files_list = os.listdir(self.data_path)
            file_type = "*.json"
            for file in data_files_list:
                if fnmatch.fnmatch(file, file_type):
                    files_to_load_log.write(file)
                    files_to_load_log.write("\n")
            files_to_load_log.close()

            # Also delete any existing logs that may still be lying around
            if os.path.exists(self.logs_path + "cleaning_log.txt"):
                os.remove(self.logs_path + "cleaning_log.txt")
            if os.path.exists(self.logs_path + "loaded_files.txt"):
                os.remove(self.logs_path + "loaded_files.txt")

    def next_file_available(self):
        ''' Checks if there's another file available in the files_to_load.txt log. If there's a
        file available, returns True. If no files are remaining, returns False so we can stop
        reading in data. '''
        files_to_load_log  = open(self.logs_path + "/files_to_load.txt", "r")
        next_file_name = files_to_load_log.readline().rstrip("\n")
        if next_file_name == '':
            return(False)
        else:
            return(True)

    def get_next_file(self):
        ''' Reads from the files_to_load.txt file and gets the name of the next file in the list.
        Calls read_file() to read in the target file in as list of dictionaries. Returns a tuple
        that includes the list of dictionaries representing the JSON data, along with the filename
        so we can keep track of this file in subsequent tasks. '''
        files_to_load_log  = open(self.logs_path + "/files_to_load.txt", "r")
        next_file_name = files_to_load_log.readline().rstrip("\n") # strip the newline character from the end of filename
        print("Extractor: Next file is: " + next_file_name)
        next_file_path = self.data_path + next_file_name
        return(self.read_data_file(next_file_path), next_file_name)

    def read_data_file(self, file_to_read):
        ''' Reads the JSON-formatted file line by line and returns each line as a dictionary. '''
        print("Extractor: Reading file: " + file_to_read)
        reading_file = open(file_to_read, "r") # open as read-only
        list_of_jsondicts = []
        for line in reading_file.readlines():
            list_of_jsondicts.append(json.loads(line))
        print("Extractor: Read " + str(len(list_of_jsondicts)) + " data rows.")
        return(list_of_jsondicts)


## Cleaner

class Cleaner:
    ''' Takes a batch of data that's been extracted as a list of dictionaries.  Contains methods to
    iterate over each record in the list, running it through a series of cleaning steps. Logs the
    ids of the records that are affected by the various cleaning steps. Returns the cleaned data back
    as a list. '''

    def __init__(self, data_list, file_name, logs_path):
        self.data_list = data_list
        self.logs_path = logs_path
        self.file_name = file_name

    def clean_data(self):
        ''' Iterates over each data element, progressing through each cleaning step on each element.
        Because dictionaries are mutable, this function can essentially perform an 'update in place'
        on the dictionary object representing the record for any values that need to be changed or corrected.
        Logs the ids of data elements that contain nulls and/or errors to arrays as we go. At the end
        of cleaning, invokes the log_cleaning() method to record a log of which records needed to have
        their geodata cleaned. '''

        step1_log = []
        step2_log = []

        #i = 0
        for record in self.data_list:
            #print(i)
            self.set_data_types(record)
            self.fix_null_places(record, step1_log)
            self.fix_bounding_box(record, step2_log)
            self.get_centroid(record)
            #i += 1

        print("Cleaner: Finished cleaning records.")
        self.log_cleaning(step1_log, step2_log)
        return(self.data_list)

    def set_data_types(self, record):
        record['id_str'] = str(record['id_str'])
        record['timestamp_ms'] = int(record['timestamp_ms'])

    def fix_null_places(self, record, log_array):
        ''' Since place values are critical to our data model, substitute dummy
        values if we have a place value that equals 'None'. This will keep it from
        blowing up the database when we try to insert. '''

        def set_none_place():
            record['place'] = dict()
            record['place']['id'] = "9999999"
            record['place']['name'] = "No Place"
            record['place']['full_name'] = "No Place Available"
            record['place']['country'] = "No Country Available"
            record['place']['country_code'] = "ZZ"
            record['place']['place_type'] = "NA"
            record['place']['url'] = "NA"
            record['place']['bounding_box'] = dict() # initialize dictionary to hold bounding box
            record['place']['bounding_box']['type'] = "Polygon"
            record['place']['bounding_box']['coordinates'] = list() # initialize coordinate list w/in bounding box
            record['place']['bounding_box']['coordinates'].append([]) # append the [0] element to hold four pairs of coordinates
            record['place']['bounding_box']['coordinates'][0].append([0.0, 0.0]) # append 'dummy' coordinates
            record['place']['bounding_box']['coordinates'][0].append([0.0, 0.0])
            record['place']['bounding_box']['coordinates'][0].append([0.0, 0.0])
            record['place']['bounding_box']['coordinates'][0].append([0.0, 0.0])
            log_array.append(record["id_str"])

        # Check if the record has a 'place' attribute
        # Note: on very rare occasions, this attribute simply doesn't exist in the tweet
        if 'place' in record:
            # If record has a 'place' attribute, but it's set to 'None', then go and add dummy values
            if record['place'] is None:
                set_none_place()
            # If record has a 'place attribute', but its bounding box is invalid, then replace its data with the dummy values
            elif record['place']['bounding_box'] is None:
                record['place'] = None
                set_none_place()
            pass # if a place is present, its value is not None, and its bounding box is present, then move along without changing/setting its values
        else:
            # If record doesn't have a 'place' attribute, then initialize one before adding dummy values
            record['place'] = None
            set_none_place()

    def fix_bounding_box(self, record, log_array):
        ''' Fix a few issues that are going on with bounding boxes:
        1. Twitter Place bounding boxes only have four points. Need to close them off so they're a
        complete polygon. Take the first coordinate of the bounding box array and repeat it at the
        end of the bounding box array.
        2. If the bounding box is actually a point (i.e. all of the four points are the same), then
        "fake out" a bounding box by transforming into a small rectangle with a small buffer around
        the point.  We can recognize these by looking for place.place_type == 'poi'. '''

        #print(record['id_str'])
        original_bounding_box = record['place']['bounding_box']['coordinates'][0].copy()
        #print(original_bounding_box)
        #print(record['place']['place_type'])

        if (record['place']['place_type'] == 'poi' or record['place']['place_type'] == 'NA'):
            point_bounding_box = [[None for x in range(2)] for y in range(5)]
            point_bounding_box[0][0] = original_bounding_box[0][0] - 0.0001
            point_bounding_box[0][1] = original_bounding_box[0][1] - 0.0001
            point_bounding_box[1][0] = original_bounding_box[1][0] - 0.0001
            point_bounding_box[1][1] = original_bounding_box[1][1] + 0.0001
            point_bounding_box[2][0] = original_bounding_box[2][0] + 0.0001
            point_bounding_box[2][1] = original_bounding_box[2][1] + 0.0001
            point_bounding_box[3][0] = original_bounding_box[3][0] + 0.0001
            point_bounding_box[3][1] = original_bounding_box[3][1] - 0.0001
            point_bounding_box[4][0] = original_bounding_box[0][0] - 0.0001
            point_bounding_box[4][1] = original_bounding_box[0][1] - 0.0001
            record['place']['better_bounding_box'] = dict()
            record['place']['better_bounding_box']['type'] = "Polygon"
            record['place']['better_bounding_box']['coordinates'] = list()
            record['place']['better_bounding_box']['coordinates'].append([])
            record['place']['better_bounding_box']['coordinates'][0] = point_bounding_box
            #print(record['place']['better_bounding_box']['coordinates'])
            log_array.append(record["id_str"])
        else:
            first_coords = original_bounding_box[0]
            #print(first_coords)
            original_bounding_box.append(first_coords)
            #print(original_bounding_box)
            record['place']['better_bounding_box'] = dict()
            record['place']['better_bounding_box']['type'] = "Polygon"
            record['place']['better_bounding_box']['coordinates'] = list()
            record['place']['better_bounding_box']['coordinates'].append([])
            record['place']['better_bounding_box']['coordinates'][0] = original_bounding_box
            #print(record['place']['better_bounding_box']['coordinates'])

    def get_centroid(self, record):
        bounding_box = record['place']['better_bounding_box']['coordinates'][0];
        lower_left = bounding_box[0];
        upper_right = bounding_box[2];
        centroid_long = lower_left[0] + ((upper_right[0] - lower_left[0]) / 2);
        centroid_lat = lower_left[1] + ((upper_right[1] - lower_left[1]) / 2);
        record['place']['centroid'] = dict()
        record['place']['centroid']['type'] = "Point"
        record['place']['centroid']['coordinates'] = [centroid_long, centroid_lat]

        record['place']['centroid_geohash'] = pgh.encode(centroid_lat, centroid_long, precision=12)

    def log_cleaning(self, step1_log, step2_log):
        ''' When cleaning is done, put the cleaning log arrays into a dictionary and write the result
        to the cleaning log file. '''

        log_dict = dict()
        log_dict['file_name'] = self.file_name
        log_dict['null_places_fixed'] = step1_log
        log_dict['bounding_boxes_fixed'] = step2_log

        cleaning_log  = open(self.logs_path + "/cleaning_log.txt", "a+") # open file in append mode
        cleaning_log.write(json.dumps(log_dict))
        cleaning_log.write("\n")
        cleaning_log.close()


## Loader

class Loader:
    '''
    Contains general methods for initializing a database connection, loading data by interating over
    records and writing them one by one to the database, and logging data about the number of successful
    and failed loads to a log file. When setting up the database connection, this class invokes other
    database-specific loader classes that contain all required methods to "plug and play" with this
    generic loader class (ex: initialize_connection(), load_record(), etc.). '''

    def __init__(self, data_list, file_name, logs_path):
        self.data_list = data_list
        self.logs_path = logs_path
        self.file_name = file_name
        self.db_connection = None

    def get_connection(self, db_type, db_host, db_port, username=None, pwd=None, db_name=None, collection_name=None):
        if db_type == "mongodb":
            self.db_connection = MongoDBLoader(db_host, db_port, username, pwd, db_name, collection_name)
            self.db_connection.initialize_connection()
        if db_type == "neo4j":
            self.db_connection = Neo4jLoader(db_host, db_port, username, pwd)
            self.db_connection.initialize_connection()
        if db_type == "elasticsearch":
            self.db_connection = ElasticSearchLoader(db_host, db_port, db_name)
            self.db_connection.initialize_connection()

    def load_data(self):
        # Initialize variables we want to count so we can output them to the log file at the end of load
        begin = time.time()
        i = 0
        success_count = 0
        fail_count = 0
        fail_log = []

        print("Loader: Loading records...")
        for record in self.data_list:
            try:
                self.db_connection.load_record(record)
                success_count += 1
            except Exception as e:
                print("Couldn't load record with id: " + record['id_str'])
                #print(e)
                fail_count += 1
                fail_dict = dict()
                fail_dict['id'] = record['id_str']
                fail_dict['error'] = str(e)
                fail_log.append(fail_dict)
            #i += 1

        print("Loader: Finished loading records.")
        end = time.time()
        load_time = end - begin # compute time elapsed for load
        self.db_connection.close_connection() # close database connection
        self.log_load(load_time, success_count, fail_count, fail_log) # write load results to log

    def load_batch_data(self):
        begin = time.time()

        try:
            fail_log = self.db_connection.bulk_load_records(self.data_list)
        except Exception as e:
            print("Couldn't bulk load records because: ")
            print(str(e))
            fail_log = str(e)
            raise

        print("Loader: Finished loading records.")
        end = time.time()
        load_time = end - begin # compute time elapsed for load
        self.db_connection.close_connection() # close database connection
        self.log_load(load_time, 'NA', 'NA', fail_log) # write load results to log

    def log_load(self, load_time, success_count, fail_count, fail_log):
        ''' When load is done, record the time it took to run, number of successes, and number of failures.
        Write this info, along with file_name, as a JSON string to a log file. Then remove the name of the
        successfully loaded file from files_to_load.txt so we don't try to re-load it on the next iteration. '''

        log_dict = dict()
        log_dict['file_name'] = self.file_name
        log_dict['load_time'] = load_time
        log_dict['success_count'] = success_count
        log_dict['fail_count'] = fail_count
        log_dict['fail_log'] = fail_log
        loaded_files_log  = open(self.logs_path + "/loaded_files.txt", "a+") # open file in append mode
        loaded_files_log.write(json.dumps(log_dict))
        loaded_files_log.write("\n")
        loaded_files_log.close()

        # https://www.reddit.com/r/learnpython/comments/3xuych/least_resource_intensive_way_to_delete_first_line/
        files_to_load_log  = open(self.logs_path + "/files_to_load.txt", "r+") # open in read/write mode
        files_to_load_log.readline() # read the first line and throw it out
        remaining_files = files_to_load_log.read() # read the rest
        files_to_load_log.seek(0) # set the cursor to the top of the file
        files_to_load_log.write(remaining_files) # write the data back
        files_to_load_log.truncate() # set the file size to the current size


### MongoDBLoader

# http://api.mongodb.com/python/current/examples/bulk.html

class MongoDBLoader:

    def __init__(self, db_host, db_port, username, pwd, db_name, collection_name):
        self.connection = None
        self.client = None
        self.username = username
        self.pwd = pwd
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.collection_name = collection_name

    def initialize_connection(self):
        if self.username is None:
            print("Connecting without a username")
            self.client = pymongo.MongoClient('mongodb://' + self.db_host + ':' + self.db_port)
        else:
            print("Connecting with username: " + self.username)
            self.client = pymongo.MongoClient('mongodb://' + self.username + ':' + self.pwd + '@' + self.db_host + ':' + self.db_port)
        target_db = self.client[self.db_name]
        target_collection = target_db[self.collection_name]

        # Initialize index on tweet 'id' field so we throw an error when trying to load duplicates of the same tweet
        #target_collection.create_index([("id", pymongo.ASCENDING)], name='id_index', unique=True)
        self.connection = target_collection

    def load_record(self, record):
        self.connection.insert_one(record)

    def bulk_load_records(self, record_list):
        try:
            self.connection.insert_many(record_list, ordered = False)
        except pymongo.errors.BulkWriteError as bwe:
            fail_log = dumps(bwe.details)
            return(fail_log)


    def close_connection(self):
        self.client.close()


### Neo4jLoader

# https://neo4j.com/developer/python/
# https://www.lynda.com/Neo4j-tutorials/Use-Neo4j-driver-Python/601789/659331-4.html

class Neo4jLoader:

    def __init__(self, db_host, db_port, username, pwd):
        self.connection = None
        self.username = username
        self.pwd = pwd
        self.db_host = db_host
        self.db_port = db_port

        self.neo4j_query_string = """
            MERGE (t:Tweet {tweet_id: toInteger($tweet_id)})
            ON CREATE SET t.text = $text,
                t.lang = $lang,
                t.timestamp_ms = toInteger($timestamp_ms),
                t.favorited = $favorited,
                t.retweeted = $retweeted,
                t.retweet_count = toInteger($retweet_count),
                t.favorite_count = toInteger($favorite_count),
                t.quote_count = toInteger($quote_count),
                t.reply_count = toInteger($reply_count),
                t.coordinates = point({
                    longitude: toFloat($tweet_coordinates_long),
                    latitude: toFloat($tweet_coordinates_lat)
                })

            MERGE (u:User {user_id: toInteger($user_id)})
            SET	u.name = $user_name,
                u.screen_name = $user_screen_name,
                u.description = $user_description,
                u.location = $user_location,
                u.lang = $user_lang,
                u.time_zone = $user_time_zone,
                u.verified = $user_verified,
                u.utc_offset = $user_utc_offset,
                u.created_at = $user_created_at,
                u.listed_count = $user_listed_count,
                u.friends_count = $user_friends_count,
                u.followers_count = $user_followers_count,
                u.favourites_count = $user_favourites_count,
                u.is_translator = $user_is_translator,
                u.statuses_count = $user_statuses_count


            MERGE (t)-[:TWEETED_BY]->(u)
            MERGE (u)-[:TWEETED]->(t)

            MERGE (p:Place {place_id: toString($place_id), latitude: toFloat($place_centroid_lat), longitude: toFloat($place_centroid_long)})
            SET	p.name = $place_name,
                p.full_name = $place_full_name,
                p.country = $place_country,
                p.country_code = $place_country_code,
                p.place_type = $place_type,
                p.bounding_box_LL = point({
                    longitude: toFloat($place_bounding_box_LL_long),
                    latitude: toFloat($place_bounding_box_LL_lat)
                }),
                p.bounding_box_UR = point({
                    longitude: toFloat($place_bounding_box_UR_long),
                    latitude: toFloat($place_bounding_box_UR_lat)
                }),
                p.centroid = point({
                    longitude: toFloat($place_centroid_long),
                    latitude: toFloat($place_centroid_lat)
                })

            MERGE (t)-[:LOCATED_AT]->(p)

            WITH t, $entities_user_mentions AS mentions
            UNWIND mentions AS mention
                MERGE (mentioned_user:User {user_id: toInteger(mention.id), name: mention.name, screen_name: mention.screen_name})
                MERGE (t)-[:MENTIONS]->(mentioned_user)

            WITH t, $entities_hashtags AS hashtags
            UNWIND hashtags AS hashtag
                MERGE (h:Hashtag {hashtag_id: hashtag.text})
                MERGE (t)-[:HASHTAGS]->(h)
            """

    def initialize_connection(self):
        # Initialize Neo4j driver and start a session
        uri = 'bolt://' + self.db_host + ':' + self.db_port
        driver = GraphDatabase.driver(uri, auth=(self.username, self.pwd))
        self.connection = driver

    def load_record(self, record):
        try:
            with self.connection.session() as session:
                tx = session.begin_transaction()
                self.structure_data_for_load(tx, record)
                tx.commit()
        except Exception as e:
            print(e)

    #@staticmethod
    def structure_data_for_load(self, tx, data_element):
        tx.run(self.neo4j_query_string, parameters={
            'tweet_id': data_element['id_str'],
            'text': data_element['text'],
            'lang': data_element['lang'],
            'timestamp_ms': data_element['timestamp_ms'],
            'favorited': data_element['favorited'],
            'retweeted': data_element['retweeted'],
            'retweet_count': data_element['retweet_count'],
            'favorite_count': data_element['favorite_count'],
            'quote_count': data_element['quote_count'],
            'reply_count': data_element['reply_count'],
            'tweet_coordinates_long': data_element['coordinates']['coordinates'][0] if data_element['coordinates'] != None else None,
            'tweet_coordinates_lat': data_element['coordinates']['coordinates'][1] if data_element['coordinates'] != None else None,
            'user_id': data_element['user']['id'],
            'user_name': data_element['user']['name'],
            'user_screen_name': data_element['user']['screen_name'],
            'user_description': data_element['user']['description'],
            'user_location': data_element['user']['location'],
            'user_lang': data_element['user']['lang'],
            'user_time_zone': data_element['user']['time_zone'],
            'user_verified': data_element['user']['verified'],
            'user_utc_offset': data_element['user']['utc_offset'],
            'user_created_at': data_element['user']['created_at'],
            'user_listed_count': data_element['user']['listed_count'],
            'user_friends_count': data_element['user']['friends_count'],
            'user_followers_count': data_element['user']['followers_count'],
            'user_favourites_count': data_element['user']['favourites_count'],
            'user_is_translator': data_element['user']['is_translator'],
            'user_statuses_count': data_element['user']['statuses_count'],
            'place_id': data_element['place']['id'],
            'place_name': data_element['place']['name'],
            'place_full_name': data_element['place']['full_name'],
            'place_country': data_element['place']['country'],
            'place_country_code': data_element['place']['country_code'],
            'place_type': data_element['place']['place_type'],
            'place_bounding_box_LL_long': data_element['place']['better_bounding_box']['coordinates'][0][0][0],
            'place_bounding_box_LL_lat': data_element['place']['better_bounding_box']['coordinates'][0][0][1],
            'place_bounding_box_UR_long': data_element['place']['better_bounding_box']['coordinates'][0][2][0],
            'place_bounding_box_UR_lat': data_element['place']['better_bounding_box']['coordinates'][0][2][1],
            'place_centroid_long': data_element['place']['centroid']['coordinates'][0],
            'place_centroid_lat': data_element['place']['centroid']['coordinates'][1],
            'entities_user_mentions': data_element['entities']['user_mentions'],
            'entities_hashtags': data_element['entities']['hashtags']
        })

    def close_connection(self):
        self.connection.close()


### ElasticSearchLoader

# https://www.elastic.co/guide/en/elasticsearch/reference/current/docs-bulk.html

class ElasticSearchLoader:

    def __init__(self, db_host, db_port, db_name):
        self.connection = None
        self.client = None
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name

    def initialize_connection(self):
        self.client = Elasticsearch([{'host': self.db_host, 'port': self.db_port}])

        # Check if we can connect successfully
        if self.client.ping():
            print("Connected to ElasticSearch instance.")

            # If we're successfully connected, then create a new index (aka database) in ElasticSearch to hold the data
            if not self.client.indices.exists(self.db_name):
                # Define settings for the new index
                settings = {
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0
                    },
                    "mappings": {
                        "tweet": {
                            "properties": {
                                "text": {
                                    "type": "text"
                                },
                                "timestamp_ms": {
                                    "type": "date"
                                },
                                "place": {
                                    "properties": {
#                                         "centroid": {
#                                             "type": "geo_point"
#                                         },
                                        "better_bounding_box": {
                                            "type": "geo_shape"
                                        },
                                        "centroid_geohash": {
                                             "type": "geo_point"
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                try:
                    self.client.indices.create(index=self.db_name, body=settings)
                    print("Created new ElasticSearch index named: " + self.db_name)
                except Exception as e:
                    print("Couldn't create new index because: ")
                    print(e)
        else:
            print("Couldn't connect to ElasticSearch instance.")

    def load_record(self, record):
        try:
            self.client.index(index=self.db_name, doc_type='tweet', body=record)
        except Exception as e:
            print(e)

    def bulk_load_records(self, record_list):
        ''' Elasticsearch's bulk API requires each row of data to be interpolated
        with a separate options list that specifies the index to save the data to,
        along with a unique id and the mapping type to use when loading the record.
        So, we'll append a dictionary of options in front of every line of data
        before loading the whole thing in bulk into the database. '''
        bulk_data_formatted = []
        for record in record_list:
            op_dict = {
                "index": {
                    "_index": self.db_name,
                    "_type": "tweet",
                    "_id": record['id']
                }
            }
            bulk_data.append(op_dict)
            bulk_data.append(record)

        try:
            result = self.client.bulk(index = self.db_name, body = bulk_data_formatted, refresh = True)
            return(result)
        except Elasticsearch.ElasticsearchException as es_error:
            fail_log = dumps(es_error)
            return(fail_log)

    def close_connection(self):
        pass
