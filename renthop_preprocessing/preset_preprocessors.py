from sklearn import preprocessing
import loaders

def features_sentiment_preprocessor():
    json_loader = loaders.JSONLoader()
    preprocessor = loaders.Preprocessor()
    preprocessor.with_pipeline('main').set_loader(json_loader)
    preprocessor.add_operation(loaders.DateTimeExtractor()).add_operation(loaders.NewSimplePredictors())
    preprocessor.add_operation(loaders.LogTransform(['price_per_bedroom', 'price', 'price_per_bathroom']))
    preprocessor.add_operation(loaders.Selector(['listing_id', 'bathrooms', u'bedrooms', 'latitude', 'longitude', 'price',
                                                 'month', 'day_of_month', 'hour', 'day_of_week', 'price_per_bathroom',
                                                 'price_per_bedroom', 'num_features', 'features_len', 'num_photos']))
    merger = loaders.PandasColumnMerger(['main', 'features', 'sentiment'], on = 'listing_id')
    preprocessor.set_consumer(merger)
    preprocessor.with_pipeline('features').set_loader(loaders.CSVLoader('data/features_train.csv', 'data/features_test.csv'))
    preprocessor.set_consumer(merger)
    preprocessor.with_pipeline('sentiment').set_loader(loaders.CSVLoader('data/sentiment_train.csv', 'data/sentiment_test.csv'))
    preprocessor.set_consumer(merger)
    preprocessor.with_pipeline('merged').set_loader(merger).add_operation(loaders.ColumnDrop('listing_id'))
    preprocessor.add_operation(loaders.ToNdarray()).add_operation(preprocessing.StandardScaler())
    preprocessor.with_pipeline('response').set_loader(json_loader.select_loader('interest_level'))
    preprocessor.add_operation(loaders.Dummifier(output_cols = ['high', 'medium', 'low'])).add_operation(loaders.ToNdarray())
    return preprocessor