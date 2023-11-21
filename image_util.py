from PIL import Image

image = Image.open('images/img2.png')

new_image = image.resize((512, 512), resample=1)
new_image.save('images/image_512_1.png')
