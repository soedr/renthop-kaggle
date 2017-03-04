
import features

import numpy as np
from pandas.io.json import read_json
from pandas import DataFrame, get_dummies, read_csv

from sklearn.utils import shuffle

from datetime import datetime
import re, os

try:
    import cPickle as pickle
except:
    import pickle

OUTPUT_COLS = ['high', 'medium', 'low']

class Preprocessor(object):

    def __init__(self):
        self._fitted = False
        
        self._pipelines = []
        self._base_pipeline_operations = []
        self._base_pipeline_loader = None
        self._base_pipeline_only_train = False
        self._cur_pipeline = None

    def with_pipeline(self, pipeline = None):
        self._cur_pipeline = pipeline
        return self

    def set_loader(self, loader, only_train = False, pipeline = None):
        if pipeline is None:
            pipeline = self._cur_pipeline
        if self._fitted:
            raise Exception('Cannot set loader to an already fitted preprocessor!')
        if not callable(loader):
            raise Exception('Loader must be callable!')
        if pipeline is None:
            self._base_pipeline_loader = loader
            self._base_pipeline_only_train = only_train
        if pipeline is None and len(self._pipelines) == 0:
            pipeline = 'main'
        if pipeline is not None:
            self._create_pipeline_if_necessary(pipeline)
            pipeline = [pipeline]
        else:
            pipeline = self._pipelines
        for p in pipeline:
            setattr(self, 'loader_' + p, loader)
            setattr(self, 'only_train_' + p, only_train)
        return self

    def add_operation(self, operation, pipeline = None):
        if pipeline is None:
            pipeline = self._cur_pipeline
        if self._fitted:
            raise Exception('Cannot add operations to an already fitted preprocessor!')
        methods = dir(operation)
        if 'fit' not in methods or 'transform' not in methods:
            raise Exception('operation must implement fit and transform methods!')
        if pipeline is None:
            self._base_pipeline_operations.append(operation)
        if pipeline is None and len(self._pipelines) == 0:
            pipeline = 'main'
        if pipeline is not None:
            if pipeline not in self._pipelines:
                self._create_pipeline_if_necessary(pipeline)
                return
            pipeline = [pipeline]
        else:
            pipeline = self._pipelines
        for p in pipeline:
            if not hasattr(self, 'operations_' + p):
                setattr(self, 'operations_' + p, [])
            getattr(self, 'operations_' + p).append(operation)
        return self

    def set_consumer(self, consumer, pipeline = None):
        if pipeline is None:
            pipeline = self._cur_pipeline
        if self._fitted:
            raise Exception('Cannot set consumer to an already fitted preprocessor!')
        if 'consume' not in dir(consumer):
            raise Exception('Consumer must implement consume method!')
        if pipeline is None:
            self._base_pipeline_operations.append(operation)
        if pipeline is None and (len(self._pipelines) or\
                len(self._pipelines) == 1 and self._pipelines[0] == 'main') == 0:
            pipeline = 'main'
        if pipeline is not None:
            if pipeline not in self._pipelines:
                self._create_pipeline_if_necessary(pipeline)
            pipeline = [pipeline]
        else:
            raise Exception('Cannot set consumer to all pipelines!')
        for p in pipeline:
            setattr(self, 'consumer_' + p, consumer)
        return self

    def load_and_transform(self, test = False, verbose = 0):
        if test and not self._fitted:
            raise Exception('Cannot transform a test set before the transforms are fitted!')
        if not self._pipelines:
            raise Exception('No loaders were set!')
        for pipeline in self._pipelines:
            if not hasattr(self, 'loader_' + pipeline):
                raise Exception('Pipeline ' + pipeline + ' has no loader!')
        loaded_data = {}
        for pipeline in self._pipelines:
            if test and getattr(self, 'only_train_' + pipeline):
                if verbose == 1:
                    print "Pipeline", pipeline, "ignored as it's only set for train data."
                continue
            if verbose == 1:
                print "Pipeline", pipeline, "started."
            data = getattr(self, 'loader_' + pipeline)(test)
            if verbose == 1:
                print "Pipeline", pipeline, "loaded."
            if hasattr(self, 'operations_' + pipeline):
                for operation in getattr(self, 'operations_' + pipeline):
                    if not test:
                        operation.fit(data)
                    data = operation.transform(data)
                    if verbose == 1:
                        print "Pipeline", pipeline + ':', "done", str(operation)
            if hasattr(self, 'consumer_' + pipeline):
                data = getattr(self, 'consumer_' + pipeline).consume(data, pipeline)
            if data is not None:
                loaded_data[pipeline] = data
            if verbose == 1:
                print "Pipeline", pipeline, "finished."
        if len(loaded_data) == 1:
            loaded_data = loaded_data[loaded_data.keys()[0]]
        self._fitted = True
        return loaded_data

    def _create_pipeline_if_necessary(self, pipeline):
        if pipeline not in self._pipelines:
            self._pipelines.append(pipeline)
            setattr(self, 'loader_' + pipeline, self._base_pipeline_loader)
            setattr(self, 'operations_' + pipeline,
                    [operator for operator in self._base_pipeline_operations])
            setattr(self, 'only_train_' + pipeline, self._base_pipeline_only_train)

    def save(self, file_name):
        with open(file_name, 'wb') as f:
            pickle.dump(self, f)

    @staticmethod
    def load(file_name):
        result = None
        with open(file_name, 'rb') as f:
            result = pickle.load(f)
        return result

class BaseLoader(object):

    def __init__(self, ftrain, ftest):
        self.ftrain = ftrain
        self.ftest = ftest
        self.clear()

    def __call__(self, test = False):
        if test:
            if self.test is None:
                self.test = self._load_dataframe(self.ftest)
            return self.test
        else:
            if self.train is None:
                self.train = self._load_dataframe(self.ftrain)
            return self.train

    def select_loader(self, columns):
        return SelectorLoader(self, columns)

    @staticmethod
    def _load_dataframe(fname):
        raise NotImplementedError

    def clear(self):
        self.train = None
        self.test = None

    def __getstate__(self):
        # Make sure we're not pickling the dataframes
        odict = self.__dict__.copy()
        del odict['train']
        del odict['test']
        return odict

    def __setstate__(self, idict):
        self.__dict__.update(idict)
        self.clear()

class JSONLoader(BaseLoader):

    def __init__(self, ftrain = 'data/train.json', ftest = 'data/test.json'):
        super(JSONLoader, self).__init__(ftrain, ftest)

    @staticmethod
    def _load_dataframe(fname):
        df = read_json(os.path.expanduser(fname))
        df['created'] = df['created'].apply(lambda x: datetime.strptime(x, '%Y-%m-%d %H:%M:%S'))
        return df

class CSVLoader(BaseLoader):
    @staticmethod
    def _load_dataframe(fname):
        return read_csv(os.path.expanduser(fname))

class SelectorLoader(object):
    # This class replaces a lambda expression, that I'm concerned would
    # break the pickling. Also, a normal function would not suffice
    # in that the state (columns) must be preserved.

    def __init__(self, loader, columns):
        self.loader = loader
        self.columns = columns

    def __call__(self, test = False):
        return self.loader(test)[self.columns]

class Selector(object):
    def __init__(self, columns):
        self.columns = columns
    
    def fit(self, data):
        pass

    def transform(self, data):
        return data[self.columns]

class ColumnDrop(object):
    def __init__(self, columns):
        self.columns = columns
    
    def fit(self, data):
        pass

    def transform(self, data):
        return data.drop(self.columns, axis = 1)

class ToNdarray(object):
    def __init__(self, dtype = np.float32):
        self.dtype = dtype
    
    def fit(self, data):
        pass

    def transform(self, data):
        return np.array(data, dtype = self.dtype)

class Slicer(object):
    def __init__(self, rowslice, colslice):
        self.rowslice = rowslice
        self.colslice = colslice
    
    def fit(self):
        pass
    
    def transform(self, data):
        return data[rowslice, colslice]

class BasePipelineMerger(object):
    '''
    Subclasses must implement do_merge(self, test = False) that would set
    how to combine data from self.data.
    '''
    def __init__(self, input_pipelines):
        self.input_pipelines = input_pipelines
        self.data = {}

    def consume(self, data, pipeline):
        self.data[pipeline] = data

    def do_merge(self, test = False):
        raise NotImplementedError

    def __call__(self, test = False):
        return self.do_merge(test)

    def __getstate__(self):
        odict = self.__dict__.copy()
        del odict['data']
        return odict

    def __setstate__(self, idict):
        self.__dict__.update(idict)
        self.data = {}

class PandasColumnMerger(BasePipelineMerger):

    def __init__(self, input_pipelines, on = None):
        super(PandasColumnMerger, self).__init__(input_pipelines)
        self.on = on

    def do_merge(self, test = False):
        if self.on:
            df = self.data[self.input_pipelines[0]]
            for pipeline in self.input_pipelines[1:]:
                df = df.merge(self.data[pipeline], how = 'outer',
                              on = self.on)
            return df
        else:
            return pd.concat(self.data.values(), ignore_index = True)

class DateTimeExtractor(object):
    operations = {
        'year': lambda x: x.year,
        'month': lambda x: x.month,
        'day_of_month': lambda x: x.day,
        'hour': lambda x: x.hour + (x.minute + x.second / 60.0) / 60.0,
        'day_of_week': lambda x: x.weekday()
    }

    def __init__(self, fields = ['month', 'day_of_month', 'hour', 'day_of_week'],
                    datetime_field = 'created'):
        self.fields = fields
        self.datetime_field = datetime_field

    def fit(self, data):
        pass

    def transform(self, data):
        for field in self.fields:
            data[field] = data[self.datetime_field].apply(self.operations[field])
        return data

class NewSimplePredictors(object):
    # This is an operation
    
    def fit(self, data):
        pass
    
    def transform(self, df):
        df['price_per_bathroom'] = df['price']/(df['bathrooms']+1)
        df['price_per_bedroom'] = df['price']/(df['bedrooms']+1)
        df['desc_len'] = df['description'].apply(lambda desc: len([x for x in re.split(r'\W+', desc) if len(x) > 0]))
        df['num_features'] = df['features'].apply(len)
        df['features_len'] = df['features'].apply(lambda feats: sum([len([x for x in re.split(r'\W+', feat) if len(x) > 0]) for feat in feats]))
        df['num_photos'] = df['photos'].apply(len)
        # force all coordinates within NYC area
        df['longitude'] = df['longitude'].apply(self._bound(-74.3434, -73.62))
        df['latitude'] = df['latitude'].apply(self._bound(40.4317, 41.0721))
        return df
    
    @staticmethod
    def _bound(m, M):
        return lambda x: max(min(x, M), m)

class Dummifier(object):
    
    def __init__(self, output_cols = None, **kwargs):
        self.output_cols = output_cols
        self.kwargs = kwargs
    
    def fit(self, data):
        pass
    
    def transform(self, data):
        dummies = get_dummies(data, **(self.kwargs))
        if self.output_cols:
            return dummies[self.output_cols]
        else:
            return dummies

class FeaturesDummifier(object):
    
    def __init__(self):
        self.colnames = ['feature_' + x.replace(' ', '_') for x in features.FEATURES_MAP.keys()]
    
    def fit(self, data):
        pass
    
    def transform(self, series):
        return DataFrame(features.get_dummies_from_features(series),
                                columns = self.colnames)

class LogTransform(object):
    
    def __init__(self, cols = None):
        self.cols = cols
    
    def fit(self, data):
        pass
    
    def transform(self, data):
        if self.cols:
            data[self.cols] = data[self.cols].applymap(lambda x: np.log(x+1))
            return data
        else:
            return data.applymap(lambda x: np.log(x+1))