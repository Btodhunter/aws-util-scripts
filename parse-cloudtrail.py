import argparse
import json
import gzip
import os

parser = argparse.ArgumentParser()
parser.add_argument("rootDir", help="Path to the directory that cloudtrail zip files are located")
parser.add_argument("SearchKey", help="The search Key you're looking for (eg. 'imageId', 'snapshotId', ect)")
parser.add_argument("SearchValue", help="The search value that you need (eg. AMI-id or Instance-id)")

args = parser.parse_args()

rootDir = args.rootDir
searchValue = args.SearchValue
searchKey = args.SearchKey

def main():
    allFiles = get_files(rootDir)
    process_files(allFiles)


def recurse(d):
    if type(d) == dict:
        if searchKey in d.keys():
            if d[searchKey] == searchValue:
                return True
        else:
            for k in d:
                if recurse(d[k]):
                    print json.dumps(d, indent=4, sort_keys=True)


def get_files(directory):
    all_files = []
    for subdir, dirs, files in os.walk(directory):
        for f in files:
            all_files.append(os.path.join(subdir, f))

    return all_files


def process_files(all_files):
    for logs in all_files:
        with gzip.open(logs, 'rb') as f:
            logfile = f.read()

        data = json.loads(logfile)

        for event in data['Records']:
            recurse(event)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(error)
