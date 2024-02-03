import asyncio
import twitter

ACCOUNT = twitter.Account("auth_token")
IMAGE = open(f"image.png", "rb").read()


async def update_profile_images(account: twitter.Account, image: bytes):
    async with twitter.Client(account) as twitter_client:
        media_id = await twitter_client.upload_image(image)
        avatar_image_url = await twitter_client.update_profile_avatar(media_id)
        banner_image_url = await twitter_client.update_profile_banner(media_id)
        print(f"Avatar URL: {avatar_image_url}")
        print(f"Banner URL: {banner_image_url}")

if __name__ == '__main__':
    asyncio.run(update_profile_images(ACCOUNT, IMAGE))
