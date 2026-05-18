ak = 'AQgefyCKCLKdB9nN9LtRfAdJnMnhk3Gt'                                     
  sk = 'PAKGrnfBPyNk3GeNHtC8fKC3PDHNFEkK'                                                                                                                         
  token = jwt.encode({'iss':ak,'exp':int(time.time())+1800,'nbf':int(time.time())-5}, sk, headers={'alg':'HS256','typ':'JWT'})
  r = requests.post('https://api.klingai.com/v1/images/generations', headers={'Authorization':f'Bearer                                          
  {token}','Content-Type':'application/json'}, json={'prompt':'a red apple','n':1,'aspect_ratio':'1:1'})                                        
  print(f'Status: {r.status_code}')                                                                                                             
  print(r.text[:300])
