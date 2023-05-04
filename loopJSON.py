import jsonlines

key = "tableLayout"
counter = 0
with jsonlines.open("baddata_results_20230502_125444.jl") as reader:
        for obj in reader:
            if key in obj and obj[key] is True:
                counter += 1
                print(obj['url'])
                

print(f"found {counter} in {key}")